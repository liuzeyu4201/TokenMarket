package application

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

// ChatPoster 出站端口。
type ChatPoster interface {
	PostJSON(ctx context.Context, apiKey string, body []byte, stream bool) volcano.ChatCallResult
	PostStream(ctx context.Context, apiKey string, body []byte) (*http.Response, error)
}

// ChatService 同进程 Chat Completions 适配。
type ChatService struct {
	Cfg     chatcompat.Config
	Client  ChatPoster
	Now     func() time.Time
	Metrics *observability.ChatMetrics
	Logger  *slog.Logger
}

func NewChatService(cfg chatcompat.Config) *ChatService {
	client := volcano.NewChatClient(cfg.BaseURL)
	if cfg.MaxResponseBytes > 0 {
		client.MaxResponseBytes = int64(cfg.MaxResponseBytes)
	}
	return &ChatService{
		Cfg:     cfg,
		Client:  client,
		Now:     func() time.Time { return time.Now().UTC() },
		Metrics: observability.DefaultChatMetrics(),
		Logger:  slog.Default(),
	}
}

func (s *ChatService) mmap() chatcompat.ModelMap {
	return chatcompat.ModelMap{Allowlist: s.Cfg.Allowlist, PublicToUpstream: s.Cfg.ModelMap}
}

func (s *ChatService) boundCtx(ctx context.Context) (context.Context, context.CancelFunc, bool) {
	_, has := ctx.Deadline()
	var rem time.Duration
	if dl, ok := ctx.Deadline(); ok {
		rem = time.Until(dl)
	}
	d := chatcompat.ClampDeadline(rem, has, s.Cfg.DefaultDeadlineSec, s.Cfg.MaxDeadlineSec)
	c, cancel := context.WithTimeout(ctx, d)
	return c, cancel, has
}

func (s *ChatService) finishNonStream(start time.Time, req chatcompat.ChatAdaptRequest, r chatcompat.ChatAdaptResult) chatcompat.ChatAdaptResult {
	r.CredentialRef = chatcompat.CredentialRef(req.APIKey, s.Cfg.HMACSecret)
	if r.SuggestedAction == "" {
		r.SuggestedAction = chatcompat.SuggestedActionFor(r.ErrorCategory)
	}
	dur := time.Since(start)
	plat := strings.TrimSpace(req.Platform)
	if plat == "" {
		plat = "volcano"
	}
	if s.Metrics != nil {
		s.Metrics.Observe(plat, false, string(r.ErrorCategory), dur)
	}
	if s.Logger != nil {
		s.Logger.Info("provider_chat_complete",
			"request_id", req.RequestID,
			"platform", plat,
			"stream", false,
			"error_category", string(r.ErrorCategory),
			"duration_ms", dur.Milliseconds(),
			"credential_ref", r.CredentialRef,
		)
	}
	return r
}

// Complete 非流式适配。调用方取消且尚未成功时返回 ctx.Err() 且类别非 success。
func (s *ChatService) Complete(ctx context.Context, req chatcompat.ChatAdaptRequest) (chatcompat.ChatAdaptResult, error) {
	start := time.Now()
	ctx, cancel, _ := s.boundCtx(ctx)
	defer cancel()

	if n := int64(len(req.Raw)); n > 0 && s.Cfg.MaxBodyBytes > 0 && n > int64(s.Cfg.MaxBodyBytes) {
		return s.finishNonStream(start, req, chatcompat.ChatAdaptResult{
			ErrorCategory: chatcompat.CategoryUnsupportedParameter,
			UsageStatus:   chatcompat.UsageNotApplicable,
		}), nil
	}

	body, cat := chatcompat.FilterToProviderBody(req, s.mmap())
	if cat != "" {
		return s.finishNonStream(start, req, chatcompat.ChatAdaptResult{
			ErrorCategory: cat,
			UsageStatus:   chatcompat.UsageNotApplicable,
		}), nil
	}

	res := s.Client.PostJSON(ctx, req.APIKey, body, false)
	if res.Err != nil {
		if errors.Is(res.Err, volcano.ErrResponseTooLarge) {
			return s.finishNonStream(start, req, chatcompat.ChatAdaptResult{
				ErrorCategory: chatcompat.CategoryInvalidResponse,
				UsageStatus:   chatcompat.UsageNotApplicable,
			}), nil
		}
		if chatcompat.IsCallerCancel(res.Err) || errors.Is(ctx.Err(), context.Canceled) && !errors.Is(ctx.Err(), context.DeadlineExceeded) {
			r := s.finishNonStream(start, req, chatcompat.ChatAdaptResult{
				ErrorCategory: chatcompat.CategoryTimeout,
				UsageStatus:   chatcompat.UsageNotApplicable,
			})
			// 取消与截止分离：对外仍非 success；error 返回 ctx.Err()
			if chatcompat.IsCallerCancel(ctx.Err()) || chatcompat.IsCallerCancel(res.Err) {
				r.ErrorCategory = chatcompat.CategoryTimeout
				return r, context.Canceled
			}
			r.ErrorCategory = chatcompat.ClassifyTransport(res.Err)
			return r, nil
		}
		r := s.finishNonStream(start, req, chatcompat.ChatAdaptResult{
			ErrorCategory: chatcompat.ClassifyTransport(res.Err),
			UsageStatus:   chatcompat.UsageNotApplicable,
		})
		return r, nil
	}
	if res.Status != http.StatusOK {
		cat := chatcompat.ClassifyHTTP(res.Status, res.Body)
		r := chatcompat.ChatAdaptResult{ErrorCategory: cat, UsageStatus: chatcompat.UsageNotApplicable}
		if cat == chatcompat.CategoryRateLimited {
			sec := chatcompat.ParseRetryAfter(res.RetryAfter, s.Cfg.DefaultRetryAfter, s.Cfg.MaxRetryAfter)
			r.RetryAfterSeconds = &sec
		}
		return s.finishNonStream(start, req, r), nil
	}
	out := chatcompat.NormalizeNonStream(res.Body, req.Model)
	return s.finishNonStream(start, req, out), nil
}

// Stream 流式适配：channel 在结束后关闭。至少会有一条 error/done/truncated。
func (s *ChatService) Stream(ctx context.Context, req chatcompat.ChatAdaptRequest) <-chan chatcompat.StreamEvent {
	ch, pre := s.OpenStream(ctx, req)
	if pre != nil {
		out := make(chan chatcompat.StreamEvent, 1)
		out <- chatcompat.StreamEvent{Kind: chatcompat.KindError, ErrorCategory: pre.ErrorCategory, RetryAfterSeconds: pre.RetryAfterSeconds}
		close(out)
		return out
	}
	return ch
}

// OpenStream 在写出客户端 SSE 之前完成过滤与上游连接。
// 非 nil 的 ChatAdaptResult 表示流开始前失败，调用方应返回 JSON envelope。
func (s *ChatService) OpenStream(parent context.Context, req chatcompat.ChatAdaptRequest) (<-chan chatcompat.StreamEvent, *chatcompat.ChatAdaptResult) {
	if req.Stream == nil || !*req.Stream {
		t := true
		req.Stream = &t
	}
	body, cat := chatcompat.FilterToProviderBody(req, s.mmap())
	if cat != "" {
		r := chatcompat.ChatAdaptResult{ErrorCategory: cat, UsageStatus: chatcompat.UsageNotApplicable, SuggestedAction: chatcompat.SuggestedActionFor(cat)}
		return nil, &r
	}
	ctx, cancel, _ := s.boundCtx(parent)
	resp, err := s.Client.PostStream(ctx, req.APIKey, body)
	if err != nil {
		cancel()
		cat := chatcompat.ClassifyTransport(err)
		r := chatcompat.ChatAdaptResult{ErrorCategory: cat, UsageStatus: chatcompat.UsageNotApplicable}
		return nil, &r
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		_ = resp.Body.Close()
		cancel()
		cat := chatcompat.ClassifyHTTP(resp.StatusCode, b)
		r := chatcompat.ChatAdaptResult{ErrorCategory: cat, UsageStatus: chatcompat.UsageNotApplicable}
		if cat == chatcompat.CategoryRateLimited {
			sec := chatcompat.ParseRetryAfter(resp.Header.Get("Retry-After"), s.Cfg.DefaultRetryAfter, s.Cfg.MaxRetryAfter)
			r.RetryAfterSeconds = &sec
		}
		return nil, &r
	}
	ch := make(chan chatcompat.StreamEvent, 16)
	go func() {
		defer cancel()
		defer resp.Body.Close()
		s.consumeSSE(ctx, req, resp.Body, ch)
	}()
	return ch, nil
}

func (s *ChatService) consumeSSE(ctx context.Context, req chatcompat.ChatAdaptRequest, body io.ReadCloser, ch chan chatcompat.StreamEvent) {
	start := time.Now()
	defer close(ch)
	emit := func(ev chatcompat.StreamEvent) {
		select {
		case ch <- ev:
		case <-ctx.Done():
		}
	}
	finish := func(cat chatcompat.ErrorCategory) {
		dur := time.Since(start)
		if s.Metrics != nil {
			s.Metrics.Observe(nz(req.Platform), true, string(cat), dur)
			if cat == chatcompat.CategoryTruncatedStream {
				s.Metrics.Truncated()
			}
		}
		if s.Logger != nil {
			s.Logger.Info("provider_chat_complete",
				"request_id", req.RequestID,
				"platform", nz(req.Platform),
				"stream", true,
				"error_category", string(cat),
				"duration_ms", dur.Milliseconds(),
				"credential_ref", chatcompat.CredentialRef(req.APIKey, s.Cfg.HMACSecret),
			)
		}
	}
	maxEvent := volcano.DefaultMaxSSEEventBytes
	maxLine := volcano.DefaultMaxSSELineBytes
	parser := volcano.NewSSEParserLimited(body, maxEvent, maxLine)
	yielded := 0
	sentDone := false
	public := req.Model
	var lastUsage *chatcompat.Usage

	for {
		ev, err := parser.Next()
		if err != nil {
			if errors.Is(err, volcano.ErrSSEEventTooLarge) || errors.Is(err, volcano.ErrSSELineTooLarge) {
				_ = body.Close()
				cat := chatcompat.CategoryInvalidResponse
				if yielded == 0 {
					emit(chatcompat.StreamEvent{Kind: chatcompat.KindError, ErrorCategory: cat})
					finish(cat)
					return
				}
				emit(chatcompat.StreamEvent{Kind: chatcompat.KindTruncated, ErrorCategory: chatcompat.CategoryTruncatedStream})
				finish(chatcompat.CategoryTruncatedStream)
				return
			}
			if yielded == 0 {
				cat := chatcompat.ClassifyTransport(err)
				if errors.Is(err, io.EOF) {
					cat = chatcompat.CategoryInvalidResponse
				}
				if chatcompat.IsCallerCancel(ctx.Err()) {
					emit(chatcompat.StreamEvent{Kind: chatcompat.KindError, ErrorCategory: cat})
					finish(cat)
					return
				}
				emit(chatcompat.StreamEvent{Kind: chatcompat.KindError, ErrorCategory: cat})
				finish(cat)
				return
			}
			emit(chatcompat.StreamEvent{Kind: chatcompat.KindTruncated, ErrorCategory: chatcompat.CategoryTruncatedStream})
			finish(chatcompat.CategoryTruncatedStream)
			return
		}
		if volcano.IsDoneData(ev.Data) {
			if !sentDone {
				emit(chatcompat.StreamEvent{Kind: chatcompat.KindDone, Usage: lastUsage})
				sentDone = true
			}
			finish(chatcompat.CategorySuccess)
			return
		}
		if u := parseStreamUsage(ev.Data); u != nil {
			lastUsage = u
		}
		if !json.Valid([]byte(ev.Data)) {
			if yielded == 0 {
				emit(chatcompat.StreamEvent{Kind: chatcompat.KindError, ErrorCategory: chatcompat.CategoryInvalidResponse})
				finish(chatcompat.CategoryInvalidResponse)
				return
			}
			emit(chatcompat.StreamEvent{Kind: chatcompat.KindTruncated, ErrorCategory: chatcompat.CategoryTruncatedStream})
			finish(chatcompat.CategoryTruncatedStream)
			return
		}
		chunk := chatcompat.StreamEvent{
			Kind:    chatcompat.KindDelta,
			Object:  "chat.completion.chunk",
			Model:   public,
			Choices: json.RawMessage(extractChoices(ev.Data)),
		}
		chunk.ID = jsonStringField(ev.Data, "id")
		emit(chunk)
		yielded++
	}
}

func parseStreamUsage(data string) *chatcompat.Usage {
	var obj map[string]json.RawMessage
	if json.Unmarshal([]byte(data), &obj) != nil {
		return nil
	}
	raw, ok := obj["usage"]
	if !ok || len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	var parsed chatcompat.Usage
	if json.Unmarshal(raw, &parsed) != nil {
		return nil
	}
	if parsed.PromptTokens == nil && parsed.CompletionTokens == nil && parsed.TotalTokens == nil {
		return nil
	}
	parsed.Source = "upstream"
	return &parsed
}

func extractChoices(data string) []byte {
	var obj map[string]json.RawMessage
	if json.Unmarshal([]byte(data), &obj) != nil {
		return []byte(data)
	}
	if c, ok := obj["choices"]; ok {
		return c
	}
	return []byte("[]")
}

func jsonStringField(data, key string) string {
	var obj map[string]json.RawMessage
	if json.Unmarshal([]byte(data), &obj) != nil {
		return ""
	}
	var s string
	_ = json.Unmarshal(obj[key], &s)
	return s
}

func nz(s string) string {
	if strings.TrimSpace(s) == "" {
		return "volcano"
	}
	return s
}

package httpserver

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keypool"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageobs"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

// ProxyDeps 公开代理路径依赖（SF12/SF15）。
type ProxyDeps struct {
	Auth      proxyauth.Authenticator
	Pool      *keypool.Pool
	Chat      *application.ChatService
	Usage     usageobs.Sink
	Metrics   *observability.ProxyHTTPMetrics
	Enabled   bool
	WriteIdle time.Duration
}

func (s *Server) registerProxy(d ProxyDeps) {
	s.engine.POST("/v1/proxy/volcano/chat/completions", s.handleProxy(d))
}

func (s *Server) handleProxy(d ProxyDeps) gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()
		rec, ok := d.Auth.Authenticate(c.GetHeader("Authorization"))
		if !ok {
			if d.Metrics != nil {
				d.Metrics.AuthFail()
				d.Metrics.ObserveRequest("volcano", "false", "auth_error", time.Since(start))
			}
			writeEnvelope(c, http.StatusUnauthorized, "INVALID_API_KEY", "代理 Key 无效")
			return
		}
		raw, err := io.ReadAll(io.LimitReader(c.Request.Body, 2<<20))
		if err != nil {
			if d.Metrics != nil {
				d.Metrics.ObserveRequest("volcano", "false", "client_error", time.Since(start))
			}
			writeEnvelope(c, http.StatusBadRequest, "INVALID_REQUEST", "无法读取请求体")
			return
		}
		req, cat := chatcompat.ParseRequestJSON(raw)
		if cat != "" {
			if d.Metrics != nil {
				d.Metrics.ObserveRequest("volcano", "false", "client_error", time.Since(start))
			}
			writeEnvelope(c, http.StatusBadRequest, "INVALID_REQUEST", "请求不符合兼容契约")
			return
		}
		sk, ok := d.Pool.Pick(rec.BuyerID)
		if !ok {
			if d.Metrics != nil {
				d.Metrics.CapacityReject()
				d.Metrics.ObserveRequest("volcano", "false", "no_capacity", time.Since(start))
			}
			writeEnvelope(c, http.StatusServiceUnavailable, "NO_AVAILABLE_KEY", "暂无可用上游 Key")
			return
		}
		defer d.Pool.Release(sk.ID)

		req.Platform = "volcano"
		req.APIKey = sk.APIKey
		clientRID := c.GetString("request_id")
		usageID := usageobs.NewEventID()
		if usageID == "" {
			usageID = rec.KeyID
		}
		req.RequestID = usageID
		if req.RequestID == "" {
			req.RequestID = rec.KeyID
		}

		observe := func(status int, res chatcompat.ChatAdaptResult, end string, partial bool) {
			if d.Usage == nil {
				return
			}
			src := "not_available"
			if res.UsageStatus == chatcompat.UsageComplete {
				src = "upstream"
			} else if res.UsageStatus == chatcompat.UsageMissing || res.UsageStatus == chatcompat.UsageInconsistent {
				src = "not_available"
			}
			obs := usageobs.Observation{
				RequestID:       req.RequestID,
				ClientRequestID: clientRID,
				ProxyKeyID:      rec.KeyID,
				APIKeyID:        sk.ID,
				BuyerID:         rec.BuyerID,
				SellerID:        sk.SellerID,
				Platform:        "volcano",
				Model:           req.Model,
				UsageSource:     src,
				Partial:         partial,
				LatencyMS:       time.Since(start).Milliseconds(),
				StatusCode:      status,
				EndReason:       end,
			}
			if res.Usage != nil {
				obs.PromptTokens = res.Usage.PromptTokens
				obs.CompletionTokens = res.Usage.CompletionTokens
				obs.TotalTokens = res.Usage.TotalTokens
				if res.UsageStatus == chatcompat.UsageComplete {
					obs.UsageSource = "official"
				}
			}
			if err := d.Usage.Observe(c.Request.Context(), obs); err != nil {
				if d.Metrics != nil {
					d.Metrics.Usage("failed")
				}
			} else if d.Metrics != nil {
				d.Metrics.Usage("accepted")
			}
		}

		stream := req.Stream != nil && *req.Stream
		streamLabel := "false"
		if stream {
			streamLabel = "true"
		}
		finishHTTP := func(status int) {
			if d.Metrics != nil {
				d.Metrics.ObserveRequest("volcano", streamLabel, observability.ResultClass(status), time.Since(start))
			}
		}

		if stream {
			s.writeStream(c, d, req, rec, sk, observe, finishHTTP)
			return
		}

		res, err := d.Chat.Complete(c.Request.Context(), req)
		if err != nil && res.ErrorCategory == chatcompat.CategorySuccess {
			writeEnvelope(c, http.StatusGatewayTimeout, "UPSTREAM_TIMEOUT", "上游超时")
			observe(http.StatusGatewayTimeout, res, "timeout", false)
			finishHTTP(http.StatusGatewayTimeout)
			return
		}
		if res.ErrorCategory != chatcompat.CategorySuccess {
			st, code, msg := mapUpstream(res.ErrorCategory)
			if res.ErrorCategory == chatcompat.CategoryRateLimited {
				cooldownKey(d.Pool, sk.ID, res.RetryAfterSeconds)
			}
			writeEnvelopeRetry(c, st, code, msg, res.RetryAfterSeconds)
			observe(st, res, string(res.ErrorCategory), false)
			finishHTTP(st)
			return
		}
		c.Header("X-Request-ID", clientRID)
		c.JSON(http.StatusOK, gin.H{
			"id":      res.ID,
			"object":  res.Object,
			"created": res.Created,
			"model":   res.Model,
			"choices": res.Choices,
			"usage":   res.Usage,
		})
		observe(http.StatusOK, res, "success", false)
		finishHTTP(http.StatusOK)
	}
}

func (s *Server) writeStream(c *gin.Context, d ProxyDeps, req chatcompat.ChatAdaptRequest, rec proxyauth.Record, sk keypool.SellerKey, observe func(int, chatcompat.ChatAdaptResult, string, bool), finishHTTP func(int)) {
	_ = rec
	writeIdle := d.WriteIdle
	if writeIdle <= 0 {
		writeIdle = DefaultSSEWriteIdle
	}
	ctx, cancel := context.WithCancel(c.Request.Context())
	defer cancel()
	ch, pre := d.Chat.OpenStream(ctx, req)
	if pre != nil {
		st, code, msg := mapUpstream(pre.ErrorCategory)
		if pre.ErrorCategory == chatcompat.CategoryRateLimited {
			cooldownKey(d.Pool, sk.ID, pre.RetryAfterSeconds)
		}
		writeEnvelopeRetry(c, st, code, msg, pre.RetryAfterSeconds)
		observe(st, *pre, string(pre.ErrorCategory), false)
		finishHTTP(st)
		return
	}
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("X-Request-ID", c.GetString("request_id"))
	c.Status(http.StatusOK)
	flusher, _ := c.Writer.(http.Flusher)
	rc := http.NewResponseController(c.Writer)
	writeChunk := func(p []byte) error {
		if err := rc.SetWriteDeadline(time.Now().Add(writeIdle)); err != nil && !errors.Is(err, http.ErrNotSupported) {
			return err
		}
		if _, err := c.Writer.Write(p); err != nil {
			return err
		}
		if flusher != nil {
			flusher.Flush()
		}
		return nil
	}
	var last chatcompat.StreamEvent
	yielded := 0
	failWrite := func() {
		cancel()
		observe(http.StatusOK, chatcompat.ChatAdaptResult{ErrorCategory: chatcompat.CategoryTimeout}, "write_idle", yielded > 0)
		finishHTTP(http.StatusOK)
	}
	for ev := range ch {
		last = ev
		if ev.Kind == chatcompat.KindError {
			if ev.ErrorCategory == chatcompat.CategoryRateLimited {
				cooldownKey(d.Pool, sk.ID, ev.RetryAfterSeconds)
			}
			code, msg := sseErrorFields(ev.ErrorCategory)
			if err := writeSSEErrorBytes(writeChunk, code, msg); err != nil {
				failWrite()
				return
			}
			if yielded == 0 {
				observe(http.StatusOK, chatcompat.ChatAdaptResult{ErrorCategory: ev.ErrorCategory}, string(ev.ErrorCategory), false)
			} else {
				observe(http.StatusOK, chatcompat.ChatAdaptResult{ErrorCategory: ev.ErrorCategory}, "upstream_interrupted", true)
			}
			finishHTTP(http.StatusOK)
			return
		}
		if ev.Kind == chatcompat.KindTruncated {
			code, msg := sseErrorFields(chatcompat.CategoryTruncatedStream)
			if err := writeSSEErrorBytes(writeChunk, code, msg); err != nil {
				failWrite()
				return
			}
			observe(http.StatusOK, chatcompat.ChatAdaptResult{ErrorCategory: chatcompat.CategoryTruncatedStream}, "upstream_interrupted", true)
			finishHTTP(http.StatusOK)
			return
		}
		if ev.Kind == chatcompat.KindDone {
			if err := writeChunk([]byte("data: [DONE]\n\n")); err != nil {
				failWrite()
				return
			}
			res := chatcompat.ChatAdaptResult{ErrorCategory: chatcompat.CategorySuccess, Model: req.Model}
			incomplete := true
			if ev.Usage != nil {
				st, u := chatcompat.InspectUsage(ev.Usage.PromptTokens, ev.Usage.CompletionTokens, ev.Usage.TotalTokens, true)
				res.Usage = u
				res.UsageStatus = st
				incomplete = st != chatcompat.UsageComplete
			} else {
				res.UsageStatus = chatcompat.UsageMissing
			}
			end := "success"
			if incomplete {
				end = "incomplete"
			}
			observe(http.StatusOK, res, end, incomplete)
			finishHTTP(http.StatusOK)
			return
		}
		chunk := gin.H{
			"id":      ev.ID,
			"object":  "chat.completion.chunk",
			"created": ev.Created,
			"model":   ev.Model,
			"choices": json.RawMessage(ev.Choices),
		}
		b, _ := json.Marshal(chunk)
		if err := writeChunk(append(append([]byte("data: "), b...), []byte("\n\n")...)); err != nil {
			failWrite()
			return
		}
		yielded++
	}
	_ = last
	_ = sk
	if yielded > 0 {
		code, msg := sseErrorFields(chatcompat.CategoryTruncatedStream)
		writeSSEError(c, flusher, code, msg)
		observe(http.StatusOK, chatcompat.ChatAdaptResult{ErrorCategory: chatcompat.CategoryTruncatedStream}, "upstream_interrupted", true)
	} else {
		code, msg := sseErrorFields(chatcompat.CategoryInvalidResponse)
		writeSSEError(c, flusher, code, msg)
		observe(http.StatusOK, chatcompat.ChatAdaptResult{ErrorCategory: chatcompat.CategoryInvalidResponse}, "invalid_response", false)
	}
	finishHTTP(http.StatusOK)
}

func writeSSEError(c *gin.Context, flusher http.Flusher, code, message string) {
	_ = writeSSEErrorBytes(func(p []byte) error {
		if _, err := c.Writer.Write(p); err != nil {
			return err
		}
		if flusher != nil {
			flusher.Flush()
		}
		return nil
	}, code, message)
}

func writeSSEErrorBytes(write func([]byte) error, code, message string) error {
	payload, err := json.Marshal(gin.H{
		"error": gin.H{
			"message": message,
			"type":    "server_error",
			"code":    code,
		},
	})
	if err != nil {
		return err
	}
	buf := make([]byte, 0, 6+len(payload)+2)
	buf = append(buf, []byte("data: ")...)
	buf = append(buf, payload...)
	buf = append(buf, []byte("\n\n")...)
	return write(buf)
}

func sseErrorFields(cat chatcompat.ErrorCategory) (code, message string) {
	_, code, message = mapUpstream(cat)
	if cat == chatcompat.CategoryTruncatedStream {
		return "UPSTREAM_INTERRUPTED", "上游流中断"
	}
	return code, message
}

func cooldownKey(pool *keypool.Pool, id string, retryAfter *int) {
	if pool == nil || id == "" {
		return
	}
	d := 30 * time.Second
	if retryAfter != nil && *retryAfter > 30 {
		d = time.Duration(*retryAfter) * time.Second
	}
	pool.Cooldown(id, d)
}

package application_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

type stubPoster struct {
	n      atomic.Int32
	status int
	body   []byte
	err    error
	block  time.Duration
	stream io.ReadCloser
}

func (s *stubPoster) PostJSON(ctx context.Context, apiKey string, body []byte, stream bool) volcano.ChatCallResult {
	s.n.Add(1)
	if s.block > 0 {
		select {
		case <-ctx.Done():
			return volcano.ChatCallResult{Err: ctx.Err()}
		case <-time.After(s.block):
		}
	}
	if s.err != nil {
		return volcano.ChatCallResult{Err: s.err}
	}
	st := s.status
	if st == 0 {
		st = 200
	}
	return volcano.ChatCallResult{Status: st, Body: s.body}
}

func (s *stubPoster) PostStream(ctx context.Context, apiKey string, body []byte) (*http.Response, error) {
	s.n.Add(1)
	if s.err != nil {
		return nil, s.err
	}
	st := s.status
	if st == 0 {
		st = 200
	}
	var rc io.ReadCloser = io.NopCloser(bytes.NewReader(nil))
	if s.stream != nil {
		rc = s.stream
	} else if len(s.body) > 0 {
		rc = io.NopCloser(bytes.NewReader(s.body))
	}
	return &http.Response{StatusCode: st, Body: rc, Header: make(http.Header)}, nil
}

func chatTestCfg() chatcompat.Config {
	return chatcompat.Config{
		Allowlist:          []string{"doubao-pro-32k"},
		DefaultDeadlineSec: 60,
		MaxDeadlineSec:     300,
		MaxBodyBytes:       2097152,
		DefaultRetryAfter:  5,
		MaxRetryAfter:      300,
		HMACSecret:         "test-hmac",
	}
}

func TestCompleteRejectsOversizedProviderBody(t *testing.T) {
	st := &stubPoster{err: volcano.ErrResponseTooLarge, status: 200, body: []byte("xxxxx")}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	res, err := svc.Complete(context.Background(), chatcompat.ChatAdaptRequest{
		Platform: "volcano", Model: "doubao-pro-32k", APIKey: "sk-x",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if res.ErrorCategory != chatcompat.CategoryInvalidResponse {
		t.Fatalf("cat %s", res.ErrorCategory)
	}
	if st.n.Load() != 1 {
		t.Fatal("must still call poster")
	}
}

type closeTracker struct {
	io.ReadCloser
	closed atomic.Bool
}

func (c *closeTracker) Close() error {
	c.closed.Store(true)
	return c.ReadCloser.Close()
}

func TestStreamOversizedSSECancelsProvider(t *testing.T) {
	raw := "data: " + strings.Repeat("z", volcano.DefaultMaxSSEEventBytes+2)
	ct := &closeTracker{ReadCloser: io.NopCloser(strings.NewReader(raw))}
	st := &stubPoster{status: 200, stream: ct}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	tru := true
	ch, pre := svc.OpenStream(context.Background(), chatcompat.ChatAdaptRequest{
		Platform: "volcano", Model: "doubao-pro-32k", APIKey: "sk-x", Stream: &tru,
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	})
	if pre != nil {
		t.Fatalf("pre %+v", pre)
	}
	ev := <-ch
	if ev.ErrorCategory != chatcompat.CategoryInvalidResponse && ev.Kind != chatcompat.KindError && ev.Kind != chatcompat.KindTruncated {
		t.Fatalf("%+v", ev)
	}
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		if ct.closed.Load() {
			return
		}
		time.Sleep(5 * time.Millisecond)
	}
	t.Fatal("provider body was not closed")
}

func TestCompleteSuccessOnePost(t *testing.T) {
	body := []byte(`{"id":"1","choices":[{"index":0,"message":{"role":"assistant","content":"hi"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`)
	st := &stubPoster{body: body, status: 200}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st, Metrics: observability.NewChatMetrics()}
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	got, err := svc.Complete(context.Background(), req)
	if err != nil {
		t.Fatal(err)
	}
	if got.ErrorCategory != chatcompat.CategorySuccess {
		t.Fatalf("%s", got.ErrorCategory)
	}
	if st.n.Load() != 1 {
		t.Fatalf("calls %d", st.n.Load())
	}
}

func TestCompleteUnsupportedPlatformNoUpstream(t *testing.T) {
	st := &stubPoster{body: []byte(`{}`)}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	req := chatcompat.ChatAdaptRequest{
		Platform: "openai", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	got, _ := svc.Complete(context.Background(), req)
	if got.ErrorCategory != chatcompat.CategoryUnsupportedPlatform {
		t.Fatalf("%s", got.ErrorCategory)
	}
	if st.n.Load() != 0 {
		t.Fatalf("upstream called")
	}
}

func TestCompleteUnsupportedEndpoint(t *testing.T) {
	st := &stubPoster{}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Endpoint: "embeddings",
		Model:    "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	got, _ := svc.Complete(context.Background(), req)
	if got.ErrorCategory != chatcompat.CategoryUnsupportedEndpoint {
		t.Fatalf("%s", got.ErrorCategory)
	}
	if st.n.Load() != 0 {
		t.Fatal("called")
	}
}

func TestCompleteCancelZeroEventsNotSuccess(t *testing.T) {
	st := &stubPoster{block: 2 * time.Second}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Millisecond)
	defer cancel()
	// 用 cancel 而非 timeout：单独 cancel
	ctx2, c2 := context.WithCancel(context.Background())
	go func() {
		time.Sleep(20 * time.Millisecond)
		c2()
	}()
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	got, err := svc.Complete(ctx2, req)
	if got.ErrorCategory == chatcompat.CategorySuccess {
		t.Fatal("success on cancel")
	}
	if err == nil && got.ErrorCategory == "" {
		t.Fatal("empty")
	}
	_ = ctx
	_ = strings.TrimSpace
}

func TestCompleteRateLimitedRetryAfter(t *testing.T) {
	st := &stubPoster{status: 429, body: []byte(`{"error":"rl"}`)}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	got, _ := svc.Complete(context.Background(), req)
	if got.ErrorCategory != chatcompat.CategoryRateLimited {
		t.Fatalf("%s", got.ErrorCategory)
	}
	if got.RetryAfterSeconds == nil || *got.RetryAfterSeconds != 5 {
		t.Fatalf("%v", got.RetryAfterSeconds)
	}
}

func TestNewChatServiceConstructs(t *testing.T) {
	svc := application.NewChatService(chatTestCfg())
	if svc == nil || svc.Client == nil {
		t.Fatal("nil")
	}
}

func TestCompleteDoesNotRetry(t *testing.T) {
	st := &stubPoster{status: 502, body: []byte(`{}`)}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	got, _ := svc.Complete(context.Background(), req)
	if got.ErrorCategory != chatcompat.CategoryTemporaryUnavailable {
		t.Fatalf("%s", got.ErrorCategory)
	}
	if st.n.Load() != 1 {
		t.Fatalf("retries %d", st.n.Load())
	}
}

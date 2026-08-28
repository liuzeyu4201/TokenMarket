package httpserver_test

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keypool"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageobs"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/httpserver"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

type memStore struct{ rec proxyauth.Record }

const testProxySecret = "tmk-0123456789abcdef0123456789abcdef"

func (m memStore) Lookup(h string) (proxyauth.Record, bool) {
	if h == proxyauth.HashSecret([]byte("pep"), testProxySecret) {
		return m.rec, true
	}
	return proxyauth.Record{}, false
}

type stubPoster struct {
	n      atomic.Int32
	status int
	body   []byte
	err    error
	stream io.ReadCloser
}

func (s *stubPoster) PostJSON(ctx context.Context, apiKey string, body []byte, stream bool) volcano.ChatCallResult {
	s.n.Add(1)
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

func chatCfg() chatcompat.Config {
	return chatcompat.Config{
		Allowlist:          []string{"doubao-pro-32k"},
		DefaultDeadlineSec: 60,
		MaxDeadlineSec:     300,
		MaxBodyBytes:       2097152,
		DefaultRetryAfter:  5,
		MaxRetryAfter:      300,
		HMACSecret:         "t",
	}
}

func proxyHandler(t *testing.T, poster *stubPoster, pool *keypool.Pool, buyer string, usage usageobs.Sink) http.Handler {
	t.Helper()
	chat := &application.ChatService{Cfg: chatCfg(), Client: poster}
	if pool == nil {
		pool = keypool.New([]keypool.SellerKey{{
			ID: "sk1", SellerID: "seller-9", APIKey: "sk-synthetic-upstream", Admin: "active", Health: "healthy",
		}}, 8)
	}
	srv, err := httpserver.NewServer(httpserver.Config{
		Service: "proxy-gateway", Version: "0.1.0",
		Proxy: &httpserver.ProxyDeps{
			Enabled: true,
			Auth: proxyauth.Authenticator{Pepper: []byte("pep"), Store: memStore{rec: proxyauth.Record{
				KeyID: "pk1", BuyerID: buyer, Platform: "volcano", Status: "active",
			}}},
			Pool:      pool,
			Chat:      chat,
			Usage:     usage,
			WriteIdle: 80 * time.Millisecond,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	return srv.Handler()
}

func TestPublicServerMountsProxyWhenEnabled(t *testing.T) {
	h := proxyHandler(t, &stubPoster{}, nil, "buyer-1", nil)
	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(`{}`))
	h.ServeHTTP(w, req)
	if w.Code == http.StatusNotFound {
		t.Fatal("proxy route not mounted")
	}
}

func TestProxyUnauthorizedEnvelope(t *testing.T) {
	h := proxyHandler(t, &stubPoster{}, nil, "buyer-1", nil)
	w := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", bytes.NewReader([]byte(`{}`)))
	h.ServeHTTP(w, req)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("code %d", w.Code)
	}
	var obj map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &obj); err != nil {
		t.Fatal(err)
	}
	if obj["code"] != "INVALID_API_KEY" || obj["request_id"] == nil {
		t.Fatalf("%v", obj)
	}
}

func TestProxySchemaError400(t *testing.T) {
	st := &stubPoster{}
	h := proxyHandler(t, st, nil, "buyer-1", nil)
	w := httptest.NewRecorder()
	body := `{"model":"doubao-pro-32k","messages":[{"role":"user","content":"hi"}],"tools":[]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("code %d %s", w.Code, w.Body.String())
	}
	if st.n.Load() != 0 {
		t.Fatal("upstream")
	}
}

func TestProxySuccessOpenAIBodyAndUsage(t *testing.T) {
	up := []byte(`{"id":"chatcmpl-1","object":"chat.completion","created":1,"model":"ep","choices":[{"index":0,"message":{"role":"assistant","content":"hi"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`)
	st := &stubPoster{status: 200, body: up}
	sink := usageobs.NewMemorySink()
	h := proxyHandler(t, st, nil, "buyer-1", sink)
	w := httptest.NewRecorder()
	body := `{"model":"doubao-pro-32k","messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testProxySecret)
	req.Header.Set("X-Request-ID", "rid-success")
	h.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatalf("code %d %s", w.Code, w.Body.String())
	}
	var obj map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &obj); err != nil {
		t.Fatal(err)
	}
	if obj["object"] != "chat.completion" || obj["error"] != nil {
		t.Fatalf("%v", obj)
	}
	if obj["model"] != "doubao-pro-32k" {
		t.Fatalf("model rewrite %v", obj["model"])
	}
	if w.Header().Get("X-Request-ID") != "rid-success" {
		t.Fatal(w.Header().Get("X-Request-ID"))
	}
	if st.n.Load() != 1 {
		t.Fatal("calls")
	}
	if sink.Len() != 1 {
		t.Fatalf("usage len %d", sink.Len())
	}
	obs := sink.All()[0]
	if obs.RequestID == "rid-success" {
		t.Fatal("usage identity must not be the client X-Request-ID")
	}
	if obs.ClientRequestID != "rid-success" {
		t.Fatalf("client correlation %q", obs.ClientRequestID)
	}
	if obs.UsageSource != "official" || obs.BuyerID != "buyer-1" {
		t.Fatalf("%+v", obs)
	}
}

func TestProxyRateLimited429(t *testing.T) {
	st := &stubPoster{status: 429, body: []byte(`{"error":"rl"}`)}
	h := proxyHandler(t, st, nil, "buyer-1", nil)
	w := httptest.NewRecorder()
	body := `{"model":"doubao-pro-32k","messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w, req)
	if w.Code != http.StatusTooManyRequests {
		t.Fatalf("code %d %s", w.Code, w.Body.String())
	}
	var obj map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &obj)
	if obj["code"] != "RATE_LIMITED" {
		t.Fatalf("%v", obj)
	}
}

func TestProxy429CooldownsSellerKey(t *testing.T) {
	st := &stubPoster{status: 429, body: []byte(`{"error":"rl"}`)}
	pool := keypool.New([]keypool.SellerKey{
		{ID: "only", SellerID: "seller-z", APIKey: "sk-up", Admin: "active", Health: "healthy"},
	}, 8)
	h := proxyHandler(t, st, pool, "buyer-1", nil)
	body := `{"model":"doubao-pro-32k","messages":[{"role":"user","content":"hi"}]}`
	w1 := httptest.NewRecorder()
	req1 := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req1.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w1, req1)
	if w1.Code != http.StatusTooManyRequests {
		t.Fatalf("first %d %s", w1.Code, w1.Body.String())
	}
	w2 := httptest.NewRecorder()
	req2 := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req2.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w2, req2)
	if w2.Code != http.StatusServiceUnavailable {
		t.Fatalf("cooldown should yield no key, got %d %s", w2.Code, w2.Body.String())
	}
	if st.n.Load() != 1 {
		t.Fatalf("upstream calls %d", st.n.Load())
	}
}

func TestProxyExcludesSelfSellerKey(t *testing.T) {
	st := &stubPoster{status: 200, body: []byte(`{"id":"1","choices":[{"index":0,"message":{"role":"assistant","content":"x"},"finish_reason":"stop"}]}`)}
	pool := keypool.New([]keypool.SellerKey{
		{ID: "self", SellerID: "buyer-1", APIKey: "sk-self", Admin: "active", Health: "healthy"},
		{ID: "other", SellerID: "seller-z", APIKey: "sk-other", Admin: "active", Health: "healthy"},
	}, 8)
	h := proxyHandler(t, st, pool, "buyer-1", nil)
	w := httptest.NewRecorder()
	body := `{"model":"doubao-pro-32k","messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatalf("%d %s", w.Code, w.Body.String())
	}
}

func TestProxySSEOpenAIChunks(t *testing.T) {
	payload := "data: {\"id\":\"c1\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"a\"}}]}\n\ndata: [DONE]\n\n"
	st := &stubPoster{status: 200, stream: io.NopCloser(strings.NewReader(payload))}
	h := proxyHandler(t, st, nil, "buyer-1", nil)
	w := httptest.NewRecorder()
	body := `{"model":"doubao-pro-32k","stream":true,"messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatalf("%d %s", w.Code, w.Body.String())
	}
	ct := w.Header().Get("Content-Type")
	if !strings.Contains(ct, "text/event-stream") {
		t.Fatalf("ct %s", ct)
	}
	out := w.Body.String()
	if !strings.Contains(out, `"object":"chat.completion.chunk"`) {
		t.Fatalf("not openai chunk: %s", out)
	}
	if strings.Contains(out, `"kind"`) {
		t.Fatalf("internal event leaked: %s", out)
	}
	if !strings.Contains(out, "data: [DONE]") {
		t.Fatalf("missing done: %s", out)
	}
}

func TestProxySSEInvalidFirstEventWritesErrorChunk(t *testing.T) {
	st := &stubPoster{status: 200, stream: io.NopCloser(strings.NewReader("data: not-json\n\n"))}
	h := proxyHandler(t, st, nil, "buyer-1", nil)
	w := httptest.NewRecorder()
	body := `{"model":"doubao-pro-32k","stream":true,"messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatalf("%d %s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Header().Get("Content-Type"), "text/event-stream") {
		t.Fatal(w.Header().Get("Content-Type"))
	}
	out := w.Body.String()
	if !strings.Contains(out, `"error"`) {
		t.Fatalf("missing sse error: %s", out)
	}
	if strings.Contains(out, `"kind"`) {
		t.Fatalf("internal event leaked: %s", out)
	}
	if strings.Contains(out, `"code":"INVALID_REQUEST"`) && strings.Contains(out, `"request_id"`) && !strings.Contains(out, "data:") {
		t.Fatalf("json envelope mixed into sse: %s", out)
	}
	if strings.Contains(out, "data: [DONE]") {
		t.Fatalf("must not fake DONE: %s", out)
	}
}

func TestProxySSEMidStreamTruncateWritesErrorNotDone(t *testing.T) {
	payload := "data: {\"id\":\"c1\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"a\"}}]}\n\n"
	st := &stubPoster{status: 200, stream: io.NopCloser(strings.NewReader(payload))}
	h := proxyHandler(t, st, nil, "buyer-1", nil)
	w := httptest.NewRecorder()
	body := `{"model":"doubao-pro-32k","stream":true,"messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatalf("%d %s", w.Code, w.Body.String())
	}
	out := w.Body.String()
	if !strings.Contains(out, `"object":"chat.completion.chunk"`) {
		t.Fatalf("missing chunk: %s", out)
	}
	if !strings.Contains(out, `"error"`) {
		t.Fatalf("missing terminal sse error: %s", out)
	}
	if strings.Contains(out, "data: [DONE]") {
		t.Fatalf("must not fake DONE after truncate: %s", out)
	}
}

func TestProxyStreamUpstream401BeforeSSE(t *testing.T) {
	st := &stubPoster{status: 401, body: []byte(`{"error":"no"}`)}
	h := proxyHandler(t, st, nil, "buyer-1", nil)
	w := httptest.NewRecorder()
	body := `{"model":"doubao-pro-32k","stream":true,"messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w, req)
	if w.Code != http.StatusBadGateway {
		t.Fatalf("%d %s", w.Code, w.Body.String())
	}
	if strings.Contains(w.Header().Get("Content-Type"), "event-stream") {
		t.Fatal("should not start sse")
	}
	var obj map[string]any
	_ = json.Unmarshal(w.Body.Bytes(), &obj)
	if obj["code"] == nil || obj["request_id"] == nil {
		t.Fatalf("%v", obj)
	}
}

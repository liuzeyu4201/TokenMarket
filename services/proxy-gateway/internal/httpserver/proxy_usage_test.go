package httpserver_test

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageobs"
)

func TestSameClientRequestIDPersistsTwoUsageFacts(t *testing.T) {
	up := []byte(`{"id":"chatcmpl-1","object":"chat.completion","created":1,"model":"ep","choices":[{"index":0,"message":{"role":"assistant","content":"hi"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`)
	st := &stubPoster{status: 200, body: up}
	sink := usageobs.NewMemorySink()
	h := proxyHandler(t, st, nil, "buyer-1", sink)
	body := `{"model":"doubao-pro-32k","messages":[{"role":"user","content":"hi"}]}`
	for i := 0; i < 2; i++ {
		w := httptest.NewRecorder()
		req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
		req.Header.Set("Authorization", "Bearer "+testProxySecret)
		req.Header.Set("X-Request-ID", "client-repeat")
		h.ServeHTTP(w, req)
		if w.Code != 200 {
			t.Fatalf("code %d %s", w.Code, w.Body.String())
		}
		if w.Header().Get("X-Request-ID") != "client-repeat" {
			t.Fatalf("echo %s", w.Header().Get("X-Request-ID"))
		}
	}
	if sink.Len() != 2 {
		t.Fatalf("want 2 usage facts, got %d", sink.Len())
	}
	seen := map[string]struct{}{}
	for _, obs := range sink.All() {
		if obs.RequestID == "client-repeat" {
			t.Fatal("server-owned id leaked client request id")
		}
		if obs.ClientRequestID != "client-repeat" {
			t.Fatalf("correlation %+v", obs)
		}
		seen[obs.RequestID] = struct{}{}
	}
	if len(seen) != 2 {
		t.Fatalf("ids %+v", seen)
	}
}

func TestStreamTerminalUsageReachesStore(t *testing.T) {
	payload := "data: {\"id\":\"c1\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"a\"}}],\"usage\":{\"prompt_tokens\":3,\"completion_tokens\":5,\"total_tokens\":8}}\n\ndata: [DONE]\n\n"
	st := &stubPoster{status: 200, stream: io.NopCloser(strings.NewReader(payload))}
	sink := usageobs.NewMemorySink()
	h := proxyHandler(t, st, nil, "buyer-1", sink)
	w := httptest.NewRecorder()
	body := `{"model":"doubao-pro-32k","stream":true,"messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatalf("%d %s", w.Code, w.Body.String())
	}
	if sink.Len() != 1 {
		t.Fatalf("len %d", sink.Len())
	}
	obs := sink.All()[0]
	if obs.PromptTokens == nil || *obs.PromptTokens != 3 {
		t.Fatalf("prompt %+v", obs)
	}
	if obs.CompletionTokens == nil || *obs.CompletionTokens != 5 {
		t.Fatalf("completion %+v", obs)
	}
	if obs.TotalTokens == nil || *obs.TotalTokens != 8 {
		t.Fatalf("total %+v", obs)
	}
	if obs.UsageSource != "official" {
		t.Fatalf("source %s", obs.UsageSource)
	}
}

func TestStreamMissingUsageMarkedIncomplete(t *testing.T) {
	payload := "data: {\"id\":\"c1\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"a\"}}]}\n\ndata: [DONE]\n\n"
	st := &stubPoster{status: 200, stream: io.NopCloser(strings.NewReader(payload))}
	sink := usageobs.NewMemorySink()
	h := proxyHandler(t, st, nil, "buyer-1", sink)
	w := httptest.NewRecorder()
	body := `{"model":"doubao-pro-32k","stream":true,"messages":[{"role":"user","content":"hi"}]}`
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+testProxySecret)
	h.ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatalf("%d %s", w.Code, w.Body.String())
	}
	obs := sink.All()[0]
	if !obs.Partial {
		t.Fatalf("want incomplete/partial %+v", obs)
	}
	if obs.EndReason != "incomplete" {
		t.Fatalf("end %s", obs.EndReason)
	}
	if obs.UsageSource == "official" {
		t.Fatalf("must not mark official without usage %+v", obs)
	}
}

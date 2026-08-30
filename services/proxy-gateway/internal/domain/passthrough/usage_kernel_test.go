package passthrough

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageparse"
)

func TestKernelCapturesOpenAIUsage(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"id":"chatcmpl-1","usage":{"prompt_tokens":8,"completion_tokens":2,"total_tokens":10}}`))
	}))
	t.Cleanup(up.Close)
	mem := usageparse.NewMemory()
	cat := testCatalog()
	for i := range cat.Records {
		if cat.Records[i].PathTemplate == "/v1/chat/completions" {
			cat.Records[i].MeteringSource = "usage"
		}
	}
	k := &Kernel{
		Catalog:  cat,
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}},
		Capture:  mem,
	}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
	req.Header.Set("X-Request-ID", "rid-usage-1")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	got, ok := mem.Get("rid-usage-1")
	if !ok {
		t.Fatal("not captured")
	}
	if got.CostStatus != usageparse.StatusRated {
		t.Fatalf("%s", got.CostStatus)
	}
	if got.Usage.TotalTokens == nil || *got.Usage.TotalTokens != 10 {
		t.Fatalf("%+v", got.Usage)
	}
	if got.ReportedMinor != nil {
		t.Fatal("forged cost")
	}
}

func TestKernelCaptureHasNoRawBody(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`))
	}))
	t.Cleanup(up.Close)
	mem := usageparse.NewMemory()
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}},
		Capture:  mem,
	}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m","api_key":"secret"}`))
	req.Header.Set("X-Request-ID", "rid-noleak")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	got, ok := mem.Get("rid-noleak")
	if !ok {
		t.Fatal("missing capture")
	}
	raw, err := json.Marshal(got)
	if err != nil {
		t.Fatal(err)
	}
	if usageparse.Forbidden(raw) || strings.Contains(string(raw), "secret") {
		t.Fatalf("leak %s", raw)
	}
}

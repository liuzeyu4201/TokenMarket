package httpserver_test

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/passthrough"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/httpserver"
)

func TestNativePrefixMountPreservesBody(t *testing.T) {
	var got string
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		got = string(b)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"id":"chatcmpl-1"}`))
	}))
	t.Cleanup(up.Close)
	cat := &endpcatalog.Catalog{
		CatalogMajor: 1,
		Providers:    []string{"openai"},
		Records: []endpcatalog.EndpointRecord{{
			ID:           "openai.post.v1.chat.completions",
			Provider:     "openai",
			Method:       "POST",
			PathTemplate: "/v1/chat/completions",
			Stability:    "stable",
		}},
	}
	k := &passthrough.Kernel{
		Catalog:  cat,
		Selector: passthrough.StaticSelector{Up: passthrough.Upstream{BaseURL: up.URL, Credential: "sk-up"}},
	}
	srv, err := httpserver.NewServer(httpserver.Config{
		Service:     testService,
		Version:     testVersion,
		Passthrough: &httpserver.PassthroughDeps{Kernel: k, ProjectMode: "shared"},
	})
	if err != nil {
		t.Fatal(err)
	}
	body := `{"model":"gpt-test","messages":[],"extra_field":true}`
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
	if got != body {
		t.Fatalf("forwarded %s", got)
	}
	if rec.Body.String() != `{"id":"chatcmpl-1"}` {
		t.Fatalf("resp %s", rec.Body.String())
	}
}

func TestNativeUnknownPathKeepsScaffoldNotFound(t *testing.T) {
	srv, _ := newTestServer(t)
	req := httptest.NewRequest(http.MethodGet, "/definitely-missing", nil)
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"status":"not_found"`) {
		t.Fatalf("body %s", rec.Body.String())
	}
}

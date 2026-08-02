package httpserver_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/concurrency"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/httpserver"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

type stubModelsHTTP struct {
	res volcano.ModelsResult
}

func (s stubModelsHTTP) ListModels(ctx context.Context, apiKey string) volcano.ModelsResult {
	_ = ctx
	_ = apiKey
	return s.res
}

func newValidateTestServer(t *testing.T, enabled bool, token string, models volcano.ModelsResult, quota volcano.QuotaReader) http.Handler {
	t.Helper()
	cfg := providervalid.Config{
		AppEnv:             "local",
		Allowlist:          []string{"doubao-pro-32k"},
		DefaultRetryAfter:  5,
		MaxRetryAfter:      300,
		GateHMACSecret:     "t",
		GlobalConcurrency:  32,
		PerCredConcurrency: 1,
	}
	v := &application.Validator{
		Cfg:    cfg,
		Models: stubModelsHTTP{res: models},
		Quota:  quota,
		Gate:   concurrency.NewValidateGate(32, 1, "t"),
		Now:    time.Now,
	}
	var deps *httpserver.ValidateDeps
	if enabled {
		deps = &httpserver.ValidateDeps{Enabled: true, Token: token, Validator: v}
	}
	srv, err := httpserver.NewServer(httpserver.Config{
		Service: "proxy-gateway", Version: "test", Validate: deps, MountValidate: enabled,
	})
	if err != nil {
		t.Fatal(err)
	}
	return srv.Handler()
}

func TestInternalValidateOKToken(t *testing.T) {
	h := newValidateTestServer(t, true, "secret-token", volcano.ModelsResult{
		AuthOK: true, ModelIDs: []string{"doubao-pro-32k"},
	}, volcano.NoopQuotaReader{})
	body := `{"platform":"volcano","api_key":"sk-synthetic-test-key-not-real"}`
	req := httptest.NewRequest(http.MethodPost, "/internal/v1/provider-credentials/validate", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", "secret-token")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != 200 {
		t.Fatalf("code %d body %s", rr.Code, rr.Body.String())
	}
	var m map[string]any
	if err := json.Unmarshal(rr.Body.Bytes(), &m); err != nil {
		t.Fatal(err)
	}
	if m["error_category"] != "quota_unavailable" {
		t.Fatalf("%v", m)
	}
	if strings.Contains(rr.Body.String(), "sk-synthetic") {
		t.Fatal("api_key leaked in response")
	}
}

func TestInternalValidateBadToken(t *testing.T) {
	h := newValidateTestServer(t, true, "secret-token", volcano.ModelsResult{}, volcano.NoopQuotaReader{})
	req := httptest.NewRequest(http.MethodPost, "/internal/v1/provider-credentials/validate", bytes.NewBufferString(`{"platform":"volcano","api_key":"k"}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", "wrong")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != 401 {
		t.Fatalf("code %d", rr.Code)
	}
}

func TestInternalValidateDisabled(t *testing.T) {
	h := newValidateTestServer(t, false, "", volcano.ModelsResult{}, volcano.NoopQuotaReader{})
	req := httptest.NewRequest(http.MethodPost, "/internal/v1/provider-credentials/validate", bytes.NewBufferString(`{}`))
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != 404 {
		t.Fatalf("code %d", rr.Code)
	}
}

func TestInternalValidateUnsupportedPlatformHTTP200(t *testing.T) {
	h := newValidateTestServer(t, true, "tok", volcano.ModelsResult{}, volcano.NoopQuotaReader{})
	body := `{"platform":"openai","api_key":"sk-synthetic-test-key-not-real"}`
	req := httptest.NewRequest(http.MethodPost, "/internal/v1/provider-credentials/validate", bytes.NewBufferString(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", "tok")
	rr := httptest.NewRecorder()
	h.ServeHTTP(rr, req)
	if rr.Code != 200 {
		t.Fatalf("want 200 not 422, got %d %s", rr.Code, rr.Body.String())
	}
	var m map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &m)
	if m["error_category"] != "unsupported_platform" {
		t.Fatalf("%v", m)
	}
}

// TestC1PublicListenerOmitsValidateWhenNotMounted 公网 server 不挂载时 validate → 404。
func TestC1PublicListenerOmitsValidateWhenNotMounted(t *testing.T) {
	cfg := providervalid.Config{
		AppEnv: "prod", Allowlist: []string{"m1"},
		DefaultRetryAfter: 5, MaxRetryAfter: 300,
		GateHMACSecret: "t", GlobalConcurrency: 32, PerCredConcurrency: 1,
		InternalEnabled: true, InternalToken: "tok", InternalBind: "127.0.0.1",
	}
	v := &application.Validator{
		Cfg: cfg, Models: stubModelsHTTP{}, Quota: volcano.NoopQuotaReader{},
		Gate: concurrency.NewValidateGate(32, 1, "t"), Now: time.Now,
	}
	deps := &httpserver.ValidateDeps{Enabled: true, Token: "tok", Validator: v}
	public, err := httpserver.NewServer(httpserver.Config{
		Service: "proxy-gateway", Version: "test",
		Validate: deps, MountValidate: false, // C1 isolate: not on public
	})
	if err != nil {
		t.Fatal(err)
	}
	if public.HasValidateRoute() {
		t.Fatal("public must not mount validate")
	}
	req := httptest.NewRequest(http.MethodPost, "/internal/v1/provider-credentials/validate", bytes.NewBufferString(`{"platform":"volcano","api_key":"k"}`))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", "tok")
	rr := httptest.NewRecorder()
	public.Handler().ServeHTTP(rr, req)
	if rr.Code != 404 {
		t.Fatalf("public validate want 404 got %d", rr.Code)
	}

	internal, err := httpserver.NewInternalValidateServer(httpserver.Config{
		Service: "proxy-gateway", Version: "test", Validate: deps,
	})
	if err != nil {
		t.Fatal(err)
	}
	if !internal.HasValidateRoute() {
		t.Fatal("internal must mount validate")
	}
	rr2 := httptest.NewRecorder()
	internal.Handler().ServeHTTP(rr2, req)
	if rr2.Code == 404 {
		t.Fatal("internal validate must not 404")
	}
}

func TestMustIsolateInternalListener(t *testing.T) {
	c := providervalid.Config{AppEnv: "prod", InternalEnabled: true}
	if !c.MustIsolateInternalListener() {
		t.Fatal("prod enabled must isolate")
	}
	c.AppEnv = "local"
	if c.MustIsolateInternalListener() {
		t.Fatal("local should not force isolate")
	}
}

func TestInternalListenAddrLoopback(t *testing.T) {
	addr := providervalid.InternalListenAddr("127.0.0.1", "", "8080")
	if addr != "127.0.0.1:8080" {
		t.Fatalf("%s", addr)
	}
	if providervalid.PublicListenAddr("8080") != ":8080" {
		t.Fatal(providervalid.PublicListenAddr("8080"))
	}
}

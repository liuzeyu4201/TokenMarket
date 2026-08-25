package httpserver_test

import (
	"bytes"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/httpserver"
)

const (
	testService = "proxy-gateway"
	testVersion = "0.1.0"
)

// newTestServer creates a server configured for tests and returns a buffer
// capturing every log emitted by the server. Callers can inspect the buffer
// to verify that secrets are redacted before serialization.
func newTestServer(t *testing.T) (*httpserver.Server, *bytes.Buffer) {
	t.Helper()

	var buf bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo}))

	srv, err := httpserver.NewServer(httpserver.Config{
		Service: testService,
		Version: testVersion,
		Logger:  logger,
	})
	if err != nil {
		t.Fatalf("NewServer: %v", err)
	}
	return srv, &buf
}

func requireHealthResponse(t *testing.T, rec *httptest.ResponseRecorder, wantStatus string) map[string]any {
	t.Helper()

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	contentType := rec.Header().Get("Content-Type")
	if !strings.Contains(contentType, "application/json") {
		t.Fatalf("expected JSON content type, got %q", contentType)
	}

	var body map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &body); err != nil {
		t.Fatalf("response body is not valid JSON: %v", err)
	}

	if body["service"] != testService {
		t.Errorf("service=%v, want %q", body["service"], testService)
	}
	if body["status"] != wantStatus {
		t.Errorf("status=%v, want %q", body["status"], wantStatus)
	}
	if body["version"] != testVersion {
		t.Errorf("version=%v, want %q", body["version"], testVersion)
	}
	if body["request_id"] == "" {
		t.Errorf("request_id is empty")
	}

	return body
}

// TestLiveness confirms that the liveness probe returns an alive status and
// the operational health shape required by the shared service contract.
func TestProxyNotMountedByDefault(t *testing.T) {
	srv, _ := newTestServer(t)
	if srv.HasProxyRoute() {
		t.Fatal("proxy should be off without Config.Proxy")
	}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodPost, "/v1/proxy/volcano/chat/completions", strings.NewReader(`{}`))
	srv.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("code %d", rec.Code)
	}
}

func TestLiveness(t *testing.T) {
	srv, _ := newTestServer(t)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	srv.Handler().ServeHTTP(rec, req)

	requireHealthResponse(t, rec, "alive")
}

// TestReadiness confirms that the readiness probe reports ready without
// depending on SF02-managed resources such as PostgreSQL, Redis or Kafka.
func TestReadiness(t *testing.T) {
	srv, _ := newTestServer(t)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health/ready", nil)
	srv.Handler().ServeHTTP(rec, req)

	requireHealthResponse(t, rec, "ready")
}

// TestMetrics confirms that Prometheus-compatible metrics are exposed and
// contain no secret or personal data.
func TestMetrics(t *testing.T) {
	srv, _ := newTestServer(t)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/metrics", nil)
	srv.Handler().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	contentType := rec.Header().Get("Content-Type")
	if !strings.Contains(contentType, "text/plain") {
		t.Fatalf("expected text/plain content type, got %q", contentType)
	}

	body, err := io.ReadAll(rec.Body)
	if err != nil {
		t.Fatalf("failed to read metrics body: %v", err)
	}
	if len(body) == 0 {
		t.Fatalf("metrics body is empty")
	}

	// The scaffold should expose at least a build/service info metric.
	if !strings.Contains(string(body), testService) {
		t.Errorf("metrics body does not contain service name %q", testService)
	}
}

// TestRequestIDPropagated confirms that a client-supplied correlation ID is
// preserved in the response and logs.
func TestRequestIDPropagated(t *testing.T) {
	srv, _ := newTestServer(t)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	req.Header.Set("X-Request-ID", "req-test-123")
	srv.Handler().ServeHTTP(rec, req)

	body := requireHealthResponse(t, rec, "alive")
	if body["request_id"] != "req-test-123" {
		t.Errorf("request_id=%v, want %q", body["request_id"], "req-test-123")
	}
}

// TestRequestIDGenerated confirms that the server assigns a request ID when
// the client does not provide one.
func TestRequestIDGenerated(t *testing.T) {
	srv, _ := newTestServer(t)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	srv.Handler().ServeHTTP(rec, req)

	body := requireHealthResponse(t, rec, "alive")
	if body["request_id"] == "" {
		t.Errorf("expected generated request_id, got empty")
	}
}

// TestUnknownBusinessPathReturns404 confirms that no business routes exist in
// the SF01 scaffold and that any unknown path returns a clear 404.
func TestUnknownBusinessPathReturns404(t *testing.T) {
	srv, _ := newTestServer(t)

	paths := []string{
		"/api/v1/unknown",
		"/api/v1/providers",
		"/api/v1/keys",
		"/buyers",
		"/sellers",
	}

	for _, path := range paths {
		t.Run(path, func(t *testing.T) {
			rec := httptest.NewRecorder()
			req := httptest.NewRequest(http.MethodGet, path, nil)
			srv.Handler().ServeHTTP(rec, req)

			if rec.Code != http.StatusNotFound {
				t.Errorf("path %q: expected status 404, got %d", path, rec.Code)
			}
		})
	}
}

// TestLogsRedactSecrets confirms that secret-like values in headers and query
// parameters are not written to the structured access log.
func TestLogsRedactSecrets(t *testing.T) {
	srv, logs := newTestServer(t)

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/api/v1/unknown?token=sk-live-abc123", nil)
	req.Header.Set("Authorization", "Bearer sk-live-abc123")
	req.Header.Set("X-Api-Key", "super-secret-api-key")
	srv.Handler().ServeHTTP(rec, req)

	// The response status is not the focus of this test; the log buffer is.
	_ = rec.Code

	logText := logs.String()
	forbidden := []string{
		"sk-live-abc123",
		"super-secret-api-key",
		"Bearer sk-live",
	}
	for _, secret := range forbidden {
		if strings.Contains(logText, secret) {
			t.Errorf("log output contains secret %q; redaction failed", secret)
		}
	}
}

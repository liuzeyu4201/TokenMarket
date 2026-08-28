package httpserver_test

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSecretHeadersOmittedFromLogs(t *testing.T) {
	srv, buf := newTestServer(t)
	secret := "super-secret-internal-token-value"
	cookie := "session=super-secret-cookie-value"
	oversized := strings.Repeat("S", 4096)
	req := httptest.NewRequest(http.MethodGet, "/health/live", nil)
	req.Header.Set("X-Internal-Token", secret)
	req.Header.Set("x-internal-token", secret)
	req.Header.Set("Cookie", cookie)
	req.Header.Set("COOKIE", cookie)
	req.Header.Set("Authorization", "Bearer "+secret)
	req.Header.Set("X-Credential-Header", secret)
	req.Header.Set("X-Api-Key", secret)
	req.Header.Set("X-Secret-Dump", oversized)
	w := httptest.NewRecorder()
	srv.Handler().ServeHTTP(w, req)
	logs := buf.String()
	if strings.Contains(logs, secret) {
		t.Fatalf("secret leaked: %s", logs)
	}
	if strings.Contains(logs, "super-secret-cookie-value") {
		t.Fatalf("cookie leaked: %s", logs)
	}
	if strings.Contains(logs, oversized[:64]) {
		t.Fatalf("oversized secret leaked")
	}
}

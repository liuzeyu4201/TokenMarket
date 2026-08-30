package passthrough

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestResolvePrefixHostAndUnique(t *testing.T) {
	cat := testCatalog()
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", nil)
	p, path, code := Resolve(req, cat)
	if p != ProtocolOpenAI || path != "/v1/chat/completions" || code != "" {
		t.Fatalf("%s %s %s", p, path, code)
	}
	req = httptest.NewRequest(http.MethodPost, "/v1/chat/completions", nil)
	req.Host = "openai.example.test"
	p, path, code = Resolve(req, cat)
	if p != ProtocolOpenAI || path != "/v1/chat/completions" || code != "" {
		t.Fatalf("host %s %s %s", p, path, code)
	}
	req = httptest.NewRequest(http.MethodPost, "/v1/messages", nil)
	p, path, code = Resolve(req, cat)
	if p != ProtocolAnthropic || code != "" {
		t.Fatalf("unique %s %s", p, code)
	}
	req = httptest.NewRequest(http.MethodGet, "/mystery", nil)
	_, _, code = Resolve(req, cat)
	if code != CodeUnresolved {
		t.Fatalf("code %s", code)
	}
	req = httptest.NewRequest(http.MethodPost, "/v1/messages", nil)
	req.Header.Set("anthropic-version", "2023-06-01")
	p, _, code = Resolve(req, nil)
	if p != ProtocolAnthropic || code != "" {
		t.Fatalf("header %s %s", p, code)
	}
	req = httptest.NewRequest(http.MethodPost, "/v1/projects/p/locations/l/publishers/google/models/m:generateContent", nil)
	p, _, code = Resolve(req, cat)
	if p != ProtocolVertex || code != "" {
		t.Fatalf("vertex path %s %s", p, code)
	}
}

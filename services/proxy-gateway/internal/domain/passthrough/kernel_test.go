package passthrough

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

func testCatalog() *endpcatalog.Catalog {
	return &endpcatalog.Catalog{
		CatalogMajor: 1,
		Providers:    []string{"openai", "anthropic", "vertex"},
		Records: []endpcatalog.EndpointRecord{
			{
				ID:           "openai.post.v1.chat.completions",
				Provider:     "openai",
				Method:       "POST",
				PathTemplate: "/v1/chat/completions",
				Stability:    "stable",
				Transport:    "sse",
			},
			{
				ID:           "anthropic.post.v1.messages",
				Provider:     "anthropic",
				Method:       "POST",
				PathTemplate: "/v1/messages",
				Stability:    "stable",
				Transport:    "sse",
			},
			{
				ID:           "vertex.post.generate",
				Provider:     "vertex",
				Method:       "POST",
				PathTemplate: "/v1/projects/{project}/locations/{location}/publishers/{publisher}/models/{model}:generateContent",
				Stability:    "stable",
			},
			{
				ID:           "openai.get.v1.organization.users",
				Provider:     "openai",
				Method:       "GET",
				PathTemplate: "/v1/organization/users",
				Stability:    "control_plane",
			},
		},
	}
}

func kernelAgainst(t *testing.T, h http.HandlerFunc) (*Kernel, *httptest.Server, *bytes.Buffer) {
	t.Helper()
	var got bytes.Buffer
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got.Reset()
		_, _ = io.Copy(&got, r.Body)
		h(w, r)
	}))
	t.Cleanup(up.Close)
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "sk-upstream-secret"}},
		Limits:   Limits{MaxRequestBytes: 1024, UpstreamTimeout: 2 * time.Second},
	}
	return k, up, &got
}

func TestGoldenUnknownJSONAndQueryPreserved(t *testing.T) {
	cases := []struct {
		name string
		url  string
		body string
	}{
		{
			name: "openai",
			url:  "/openai/v1/chat/completions?foo=bar",
			body: `{"model":"gpt-test","messages":[{"role":"user","content":"hi"}],"custom_extra":{"keep":true}}`,
		},
		{
			name: "anthropic",
			url:  "/anthropic/v1/messages",
			body: `{"model":"claude-test","max_tokens":16,"messages":[{"role":"user","content":"hi"}],"custom_extra":1}`,
		},
		{
			name: "vertex",
			url:  "/vertex/v1/projects/p/locations/us/publishers/google/models/g:generateContent",
			body: `{"contents":[{"role":"user","parts":[{"text":"hi"}]}],"custom_extra":"x"}`,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			var sawPath, sawQuery, sawAuth, sawCookie string
			k, _, got := kernelAgainst(t, func(w http.ResponseWriter, r *http.Request) {
				sawPath = r.URL.Path
				sawQuery = r.URL.RawQuery
				sawAuth = r.Header.Get("Authorization") + r.Header.Get("x-api-key")
				sawCookie = r.Header.Get("Cookie")
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(200)
				_, _ = w.Write([]byte(`{"ok":true,"custom_echo":true}`))
			})
			req := httptest.NewRequest(http.MethodPost, tc.url, strings.NewReader(tc.body))
			req.Header.Set("Content-Type", "application/json")
			req.Header.Set("Cookie", "session=secret-cookie")
			req.Header.Set("Authorization", "Bearer buyer-key")
			req.Header.Set("X-Request-ID", "rid-1")
			rec := httptest.NewRecorder()
			k.ServeHTTP(rec, req, "shared", false)
			if rec.Code != 200 {
				t.Fatalf("status %d body %s", rec.Code, rec.Body.String())
			}
			if got.String() != tc.body {
				t.Fatalf("body mutated:\n got %s\nwant %s", got.String(), tc.body)
			}
			if strings.Contains(got.String(), "buyer-key") {
				t.Fatal("buyer credential leaked into body")
			}
			if sawCookie != "" {
				t.Fatalf("cookie forwarded: %q", sawCookie)
			}
			if !strings.Contains(sawAuth, "sk-upstream-secret") {
				t.Fatalf("upstream auth missing: %q", sawAuth)
			}
			if strings.Contains(sawAuth, "buyer-key") {
				t.Fatal("buyer authorization forwarded")
			}
			if tc.name == "openai" && sawQuery != "foo=bar" {
				t.Fatalf("query dropped: %q", sawQuery)
			}
			if tc.name == "openai" && sawPath != "/v1/chat/completions" {
				t.Fatalf("path rewritten: %q", sawPath)
			}
			if tc.name == "anthropic" && !strings.Contains(got.String(), `"messages"`) {
				t.Fatal("anthropic shape lost")
			}
			if rec.Result().Header.Get("X-Request-ID") != "rid-1" {
				t.Fatalf("request id: %q", rec.Result().Header.Get("X-Request-ID"))
			}
			if rec.Body.String() != `{"ok":true,"custom_echo":true}` {
				t.Fatalf("response mutated: %s", rec.Body.String())
			}
		})
	}
}

func TestUpstreamErrorPassedThrough(t *testing.T) {
	native := `{"type":"error","error":{"type":"rate_limited","message":"slow down"}}`
	k, _, _ := kernelAgainst(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Retry-After", "7")
		w.WriteHeader(429)
		_, _ = w.Write([]byte(native))
	})
	req := httptest.NewRequest(http.MethodPost, "/anthropic/v1/messages", strings.NewReader(`{"model":"x","max_tokens":1,"messages":[]}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != 429 {
		t.Fatalf("status %d", rec.Code)
	}
	if rec.Body.String() != native {
		t.Fatalf("body %s", rec.Body.String())
	}
	if rec.Result().Header.Get("Retry-After") != "7" {
		t.Fatalf("retry-after dropped")
	}
	if strings.Contains(rec.Body.String(), "RATE_LIMITED") && !strings.Contains(native, "RATE_LIMITED") {
		t.Fatal("platform code injected into upstream body")
	}
}

func TestControlPlanePlatformEnvelope(t *testing.T) {
	k, _, got := kernelAgainst(t, func(w http.ResponseWriter, r *http.Request) {
		t.Fatal("must not forward control plane")
	})
	req := httptest.NewRequest(http.MethodGet, "/openai/v1/organization/users", nil)
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status %d", rec.Code)
	}
	if got.Len() != 0 {
		t.Fatalf("forwarded %s", got.String())
	}
	var env map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &env); err != nil {
		t.Fatal(err)
	}
	if env["code"] != endpcatalog.CodeControlPlane {
		t.Fatalf("code %v", env["code"])
	}
	if _, ok := env["error"]; ok {
		t.Fatal("must not look like vendor error object")
	}
}

func TestUnresolvedProtocol(t *testing.T) {
	k := &Kernel{Catalog: testCatalog(), Selector: FailClosedSelector{}}
	req := httptest.NewRequest(http.MethodGet, "/unknown/path", nil)
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), CodeUnresolved) {
		t.Fatalf("body %s", rec.Body.String())
	}
}

func TestNoUpstreamFailClosed(t *testing.T) {
	k := &Kernel{Catalog: testCatalog(), Selector: FailClosedSelector{}}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), CodeNoUpstream) {
		t.Fatalf("body %s", rec.Body.String())
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func TestCancelPropagatesWithinOneSecond(t *testing.T) {
	started := make(chan struct{})
	canceled := make(chan struct{})
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: "http://127.0.0.1:9", Credential: "k"}},
		Limits:   Limits{UpstreamTimeout: 5 * time.Second},
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			close(started)
			select {
			case <-req.Context().Done():
				close(canceled)
				return nil, req.Context().Err()
			case <-time.After(5 * time.Second):
				t.Error("transport did not see cancel")
				return nil, context.DeadlineExceeded
			}
		}),
	}
	ctx, cancel := context.WithCancel(context.Background())
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`)).WithContext(ctx)
	go func() {
		<-started
		cancel()
	}()
	rec := httptest.NewRecorder()
	done := make(chan struct{})
	go func() {
		k.ServeHTTP(rec, req, "shared", false)
		close(done)
	}()
	select {
	case <-canceled:
	case <-time.After(time.Second):
		t.Fatal("cancel not observed within 1s")
	}
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("handler stuck")
	}
}

func TestRequestTooLargeNotForwarded(t *testing.T) {
	var n atomic.Int32
	k, _, _ := kernelAgainst(t, func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	})
	k.Limits.MaxRequestBytes = 16
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(strings.Repeat("a", 64)))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if n.Load() != 0 {
		t.Fatal("oversized body forwarded")
	}
	if rec.Code != http.StatusRequestEntityTooLarge && rec.Code != http.StatusBadRequest {
		// MaxBytesReader may surface via ErrorHandler as 413
		if rec.Code < 400 {
			t.Fatalf("status %d body %s", rec.Code, rec.Body.String())
		}
	}
}

func TestUpstreamTimeoutEnvelope(t *testing.T) {
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: "http://127.0.0.1:9", Credential: "k"}},
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			return nil, context.DeadlineExceeded
		}),
	}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusGatewayTimeout {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), CodeTimeout) {
		t.Fatalf("body %s", rec.Body.String())
	}
}

func TestSelectorErrorString(t *testing.T) {
	if errNoUpstream.Error() != CodeNoUpstream {
		t.Fatalf("%q", errNoUpstream.Error())
	}
}

func TestStaticSelectorSelectConnection(t *testing.T) {
	s := StaticSelector{Up: Upstream{BaseURL: "http://up", Credential: "k", ConnectionID: "conn-A"}}
	up, err := s.SelectConnection(context.Background(), "conn-A")
	if err != nil || up.ConnectionID != "conn-A" {
		t.Fatalf("%+v %v", up, err)
	}
	if _, err := s.SelectConnection(context.Background(), "conn-B"); err == nil {
		t.Fatal("expected miss on other connection")
	}
	empty := StaticSelector{Up: Upstream{BaseURL: "http://up", Credential: "k"}}
	up, err = empty.SelectConnection(context.Background(), "conn-Z")
	if err != nil || up.ConnectionID != "conn-Z" {
		t.Fatalf("%+v %v", up, err)
	}
}

func TestFailClosedSelectConnection(t *testing.T) {
	if _, err := (FailClosedSelector{}).SelectConnection(context.Background(), "c"); err == nil {
		t.Fatal("expected no upstream")
	}
}

func TestNoChatcompatImport(t *testing.T) {
	root := "."
	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() || !strings.HasSuffix(path, ".go") || strings.HasSuffix(path, "_test.go") {
			return nil
		}
		b, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		if bytes.Contains(b, []byte("chatcompat")) {
			t.Errorf("%s imports or mentions chatcompat", path)
		}
		if bytes.Contains(bytes.ToLower(b), []byte("openai-to-anthropic")) {
			t.Errorf("%s has conversion identifier", path)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}

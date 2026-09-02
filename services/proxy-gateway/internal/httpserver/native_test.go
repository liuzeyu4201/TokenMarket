package httpserver_test

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/passthrough"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/score"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/httpserver"
)

const nativeSecret = "tmk-0123456789abcdef0123456789abcdef"

func nativePepper() []byte { return []byte("native-pep") }

func nativeAuth(projectID, mode string, preview bool) proxyauth.Authenticator {
	h := proxyauth.HashSecret(nativePepper(), nativeSecret)
	return proxyauth.Authenticator{
		Pepper: nativePepper(),
		Store: proxyauth.MapStore{Records: map[string]proxyauth.Record{
			h: {
				KeyID: "pk1", BuyerID: "buyer-1", Platform: "openai", Status: "active",
				ProjectID: projectID, ProjectMode: mode, PreviewOptIn: preview,
			},
		}},
	}
}

func nativeCatalog() *endpcatalog.Catalog {
	return &endpcatalog.Catalog{
		CatalogMajor: 1,
		Providers:    []string{"openai"},
		Records: []endpcatalog.EndpointRecord{
			{
				ID:           "openai.post.v1.chat.completions",
				Provider:     "openai",
				Method:       "POST",
				PathTemplate: "/v1/chat/completions",
				Stability:    "stable",
			},
			{
				ID:           "openai.post.v1.preview.widgets",
				Provider:     "openai",
				Method:       "POST",
				PathTemplate: "/v1/preview/widgets",
				Stability:    "preview",
			},
		},
	}
}

func TestNativePrefixMountPreservesBody(t *testing.T) {
	var got string
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		got = string(b)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"id":"chatcmpl-1"}`))
	}))
	t.Cleanup(up.Close)
	store := passthrough.NewMemoryStore()
	store.Put(passthrough.ProjectSnapshot{
		ProjectID:    "proj-1",
		Mode:         "shared",
		BuyerOwnerID: "buyer-1",
		Candidates: []qualify.Candidate{{
			ConnectionID: "c1", SellerOwnerID: "seller-9", Provider: "openai", Protocol: "openai",
			SupplyMode: "shared", Lifecycle: "listed", Health: "healthy",
			DeclaredCapacity: 8, AdmitsNew: true, PriceValid: true,
			EndpointIDs: []string{"openai.post.v1.chat.completions"},
		}},
		Signals: map[string]score.Signals{"c1": {
			ConnectionID: "c1", Health: "healthy", Remaining: 8, Declared: 8,
			CapacityPresent: true, PricePresent: true, SellerBPS: 10000, LatencyPresent: true,
		}},
		Upstreams: map[string]passthrough.Upstream{"c1": {BaseURL: up.URL, Credential: "sk-up"}},
	})
	k := &passthrough.Kernel{Catalog: nativeCatalog(), Selector: passthrough.RoutingSelector{}}
	srv, err := httpserver.NewServer(httpserver.Config{
		Service: testService,
		Version: testVersion,
		Passthrough: &httpserver.PassthroughDeps{
			Kernel:    k,
			Auth:      nativeAuth("proj-1", "shared", false),
			Snapshots: store,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	body := `{"model":"gpt-test","messages":[],"extra_field":true}`
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+nativeSecret)
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

func TestNativeRejectsUnauthenticated(t *testing.T) {
	k := &passthrough.Kernel{Catalog: nativeCatalog(), Selector: passthrough.RoutingSelector{}}
	srv, err := httpserver.NewServer(httpserver.Config{
		Service:     testService,
		Version:     testVersion,
		Passthrough: &httpserver.PassthroughDeps{Kernel: k, Auth: nativeAuth("proj-1", "shared", false)},
	})
	if err != nil {
		t.Fatal(err)
	}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
}

func TestNativeIgnoresSpoofedProjectModeAndPreviewHeaders(t *testing.T) {
	var hits atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"id":"ok"}`))
	}))
	t.Cleanup(up.Close)
	store := passthrough.NewMemoryStore()
	store.Put(passthrough.ProjectSnapshot{
		ProjectID: "proj-1",
		Mode:      "shared",
		Dedicated: passthrough.DedicatedSnapshot{
			ConnectionID: "pin", Status: "active", Health: "healthy",
			Up: passthrough.Upstream{BaseURL: "http://127.0.0.1:1", Credential: "nope"},
		},
		Candidates: []qualify.Candidate{{
			ConnectionID: "c1", SellerOwnerID: "seller-9", Provider: "openai", Protocol: "openai",
			SupplyMode: "shared", Lifecycle: "listed", Health: "healthy",
			DeclaredCapacity: 8, AdmitsNew: true, PriceValid: true,
		}},
		Signals:   map[string]score.Signals{"c1": {ConnectionID: "c1", Health: "healthy", Remaining: 4, Declared: 8, CapacityPresent: true, PricePresent: true, SellerBPS: 10000}},
		Upstreams: map[string]passthrough.Upstream{"c1": {BaseURL: up.URL, Credential: "sk"}},
	})
	k := &passthrough.Kernel{Catalog: nativeCatalog(), Selector: passthrough.RoutingSelector{}}
	srv, _ := httpserver.NewServer(httpserver.Config{
		Service: testService, Version: testVersion,
		Passthrough: &httpserver.PassthroughDeps{
			Kernel: k, Auth: nativeAuth("proj-1", "shared", false), Snapshots: store,
		},
	})
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/preview/widgets", strings.NewReader(`{}`))
	req.Header.Set("Authorization", "Bearer "+nativeSecret)
	req.Header.Set("X-TokenMarket-Project-Mode", "dedicated")
	req.Header.Set("X-TokenMarket-Preview", "1")
	rec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(rec, req)
	if rec.Code != http.StatusForbidden || !strings.Contains(rec.Body.String(), "PREVIEW_NOT_ENABLED") {
		t.Fatalf("spoofed preview must not admit: %d %s", rec.Code, rec.Body.String())
	}
	if strings.Contains(rec.Body.String(), `"id":"ok"`) {
		t.Fatal("upstream must not see spoofed preview")
	}
	chat := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	chat.Header.Set("Authorization", "Bearer "+nativeSecret)
	chat.Header.Set("X-TokenMarket-Project-Mode", "dedicated")
	chatRec := httptest.NewRecorder()
	srv.Handler().ServeHTTP(chatRec, chat)
	if chatRec.Code != 200 {
		t.Fatalf("shared chat %d %s", chatRec.Code, chatRec.Body.String())
	}
	if hits.Load() != 1 {
		t.Fatalf("shared upstream hits %d (dedicated spoof must not win)", hits.Load())
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

package passthrough

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
)

func TestQualifyingSelectorNoUpstreamWhenEmpty(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	sel := &QualifyingSelector{
		Request: qualify.Request{
			BuyerOwnerID: "buyer-1",
			ProjectMode:  "shared",
			Provider:     "openai",
			Protocol:     "openai",
			EndpointID:   "openai.post.v1.chat.completions",
		},
		Candidates: []qualify.Candidate{{
			ConnectionID:     "self",
			SellerOwnerID:    "buyer-1",
			Provider:         "openai",
			Protocol:         "openai",
			SupplyMode:       "shared",
			Lifecycle:        "listed",
			Health:           "healthy",
			DeclaredCapacity: 3,
			AdmitsNew:        true,
			PriceValid:       true,
			EndpointIDs:      []string{"openai.post.v1.chat.completions"},
		}},
		Upstreams: map[string]Upstream{"self": {BaseURL: up.URL, Credential: "k"}},
	}
	k := &Kernel{Catalog: testCatalog(), Selector: sel}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
	if n.Load() != 0 {
		t.Fatal("upstream called")
	}
	if !strings.Contains(rec.Body.String(), CodeNoUpstream) {
		t.Fatalf("body %s", rec.Body.String())
	}
}

func TestQualifyingSelectorPicksQualified(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(up.Close)
	good := qualify.Candidate{
		ConnectionID:     "good",
		SellerOwnerID:    "seller-x",
		Provider:         "openai",
		Protocol:         "openai",
		SupplyMode:       "shared",
		Lifecycle:        "listed",
		Health:           "healthy",
		DeclaredCapacity: 2,
		AdmitsNew:        true,
		PriceValid:       true,
		EndpointIDs:      []string{"openai.post.v1.chat.completions"},
	}
	sel := &QualifyingSelector{
		Request:    qualify.Request{BuyerOwnerID: "buyer-1", ProjectMode: "shared"},
		Candidates: []qualify.Candidate{good},
		Upstreams:  map[string]Upstream{"good": {BaseURL: up.URL, Credential: "k"}},
	}
	k := &Kernel{Catalog: testCatalog(), Selector: sel}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if _, err := sel.Select(context.Background(), "openai", "openai.post.v1.chat.completions"); err != nil {
		t.Fatal(err)
	}
}

package passthrough

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/score"
)

func TestRoutingSelectorRequiresSnapshot(t *testing.T) {
	sel := RoutingSelector{}
	if _, err := sel.Select(context.Background(), "openai", "openai.post.v1.chat.completions"); err != errNoUpstream {
		t.Fatalf("err %v", err)
	}
}

func TestRoutingSelectorSharedUsesQualifyThenScore(t *testing.T) {
	var hits atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"id":"ok"}`))
	}))
	t.Cleanup(up.Close)
	snap := ProjectSnapshot{
		ProjectID:    "proj-shared",
		Mode:         "shared",
		BuyerOwnerID: "buyer-1",
		Candidates: []qualify.Candidate{
			scoringCand("self", "buyer-1", "shared"),
			scoringCand("ok", "seller-2", "shared"),
		},
		Signals: map[string]score.Signals{
			"self": scoringSig("self", 8),
			"ok":   scoringSig("ok", 8),
		},
		Upstreams: map[string]Upstream{"ok": {BaseURL: up.URL, Credential: "sk"}},
		Policy:    score.Policy{Version: "1.0.0"},
	}
	k := &Kernel{Catalog: testCatalog(), Selector: RoutingSelector{}}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat.completions", strings.NewReader(`{}`))
	req.URL.Path = "/openai/v1/chat/completions"
	req = req.WithContext(WithSnapshot(req.Context(), snap))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, snap.Mode, snap.PreviewOptIn)
	if rec.Code != 200 {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
	if hits.Load() != 1 {
		t.Fatalf("hits %d", hits.Load())
	}
}

func TestRoutingSelectorDedicatedNeverHitsShared(t *testing.T) {
	var sharedHits, dedicatedHits atomic.Int32
	shared := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sharedHits.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(shared.Close)
	ded := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		dedicatedHits.Add(1)
		w.WriteHeader(200)
		_, _ = io.WriteString(w, `{"id":"d"}`)
	}))
	t.Cleanup(ded.Close)
	snap := ProjectSnapshot{
		ProjectID: "proj-ded",
		Mode:      "dedicated",
		Dedicated: DedicatedSnapshot{
			ConnectionID: "pin-1",
			Status:       "active",
			Health:       "healthy",
			Up:           Upstream{BaseURL: ded.URL, Credential: "sk-d"},
		},
		Candidates: []qualify.Candidate{scoringCand("pool", "seller-2", "shared")},
		Upstreams:  map[string]Upstream{"pool": {BaseURL: shared.URL, Credential: "sk-s"}},
	}
	k := &Kernel{Catalog: testCatalog(), Selector: RoutingSelector{}}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	req = req.WithContext(WithSnapshot(req.Context(), snap))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != 200 {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
	if dedicatedHits.Load() != 1 || sharedHits.Load() != 0 {
		t.Fatalf("dedicated=%d shared=%d", dedicatedHits.Load(), sharedHits.Load())
	}
	unavail := snap
	unavail.Dedicated.Status = "faulted"
	req2 := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	req2 = req2.WithContext(WithSnapshot(req2.Context(), unavail))
	rec2 := httptest.NewRecorder()
	k.ServeHTTP(rec2, req2, "dedicated", false)
	if rec2.Code != http.StatusServiceUnavailable || !strings.Contains(rec2.Body.String(), CodeDedicatedUnavailable) {
		t.Fatalf("faulted dedicated %d %s", rec2.Code, rec2.Body.String())
	}
	if sharedHits.Load() != 0 {
		t.Fatal("dedicated fault must not fall back to shared")
	}
}

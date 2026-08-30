package passthrough

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/score"
)

func scoringCand(id, seller, mode string) qualify.Candidate {
	return qualify.Candidate{
		ConnectionID:     id,
		SellerOwnerID:    seller,
		Provider:         "openai",
		Protocol:         "openai",
		SupplyMode:       mode,
		Lifecycle:        "listed",
		Health:           "healthy",
		DeclaredCapacity: 8,
		AdmitsNew:        true,
		PriceValid:       true,
		EndpointIDs:      []string{"openai.post.v1.chat.completions"},
	}
}

func scoringSig(id string, remaining int) score.Signals {
	return score.Signals{
		ConnectionID:    id,
		Health:          "healthy",
		LatencyMS:       80,
		LatencyPresent:  true,
		Remaining:       remaining,
		Declared:        8,
		CapacityPresent: true,
		SellerBPS:       10000,
		PricePresent:    true,
	}
}

func TestScoringSelectorNoUpstreamWhenEmpty(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	sel := &ScoringSelector{
		Request: qualify.Request{
			BuyerOwnerID: "buyer-1",
			ProjectMode:  "shared",
			Provider:     "openai",
			Protocol:     "openai",
			EndpointID:   "openai.post.v1.chat.completions",
		},
		Candidates: []qualify.Candidate{scoringCand("self", "buyer-1", "shared")},
		Signals:    map[string]score.Signals{"self": scoringSig("self", 8)},
		Upstreams:  map[string]Upstream{"self": {BaseURL: up.URL, Credential: "k"}},
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

func TestScoringSelectorHardFilteredNeverWins(t *testing.T) {
	var dedicatedHits, sharedHits atomic.Int32
	ded := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		dedicatedHits.Add(1)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(ded.Close)
	shr := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sharedHits.Add(1)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(shr.Close)
	best := scoringSig("dedicated", 100)
	best.LatencyMS = 1
	best.SellerBPS = 1000
	worse := scoringSig("shared", 100)
	worse.Health = "degraded"
	worse.LatencyMS = 400
	worse.SellerBPS = 15000
	sel := &ScoringSelector{
		Request: qualify.Request{BuyerOwnerID: "buyer-1", ProjectMode: "shared"},
		Candidates: []qualify.Candidate{
			scoringCand("dedicated", "seller-d", "dedicated"),
			scoringCand("shared", "seller-s", "shared"),
		},
		Signals: map[string]score.Signals{"dedicated": best, "shared": worse},
		Policy:  score.Policy{Version: "pol-1", ExploreBPS: 10000},
		Seed:    42,
		Upstreams: map[string]Upstream{
			"dedicated": {BaseURL: ded.URL, Credential: "k"},
			"shared":    {BaseURL: shr.URL, Credential: "k"},
		},
	}
	k := &Kernel{Catalog: testCatalog(), Selector: sel}
	for i := 0; i < 20; i++ {
		req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
		rec := httptest.NewRecorder()
		k.ServeHTTP(rec, req, "shared", false)
		if rec.Code != 200 {
			t.Fatalf("%d %s", rec.Code, rec.Body.String())
		}
	}
	if dedicatedHits.Load() != 0 {
		t.Fatalf("dedicated selected %d", dedicatedHits.Load())
	}
	if sharedHits.Load() != 20 {
		t.Fatalf("shared hits %d", sharedHits.Load())
	}
	for _, id := range sel.LastFilter.QualifiedIDs {
		if id == "dedicated" {
			t.Fatal("dedicated in qualified set")
		}
	}
	if sel.LastDecision.Winner != "shared" {
		t.Fatalf("winner %s", sel.LastDecision.Winner)
	}
}

func TestScoringSelectorPicksHigherScore(t *testing.T) {
	var aHits, bHits atomic.Int32
	a := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		aHits.Add(1)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(a.Close)
	b := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		bHits.Add(1)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(b.Close)
	sa := scoringSig("a", 5)
	sb := scoringSig("b", 5)
	sb.Health = "degraded"
	sel := &ScoringSelector{
		Request: qualify.Request{BuyerOwnerID: "buyer-1", ProjectMode: "shared"},
		Candidates: []qualify.Candidate{
			scoringCand("a", "seller-a", "shared"),
			scoringCand("b", "seller-b", "shared"),
		},
		Signals:   map[string]score.Signals{"a": sa, "b": sb},
		Policy:    score.Policy{Version: "pol-1"},
		Upstreams: map[string]Upstream{"a": {BaseURL: a.URL, Credential: "k"}, "b": {BaseURL: b.URL, Credential: "k"}},
	}
	k := &Kernel{Catalog: testCatalog(), Selector: sel}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if aHits.Load() != 1 || bHits.Load() != 0 {
		t.Fatalf("hits a=%d b=%d", aHits.Load(), bHits.Load())
	}
	if sel.LastDecision.PolicyVersion != "pol-1" || sel.LastDecision.Reason == "" {
		t.Fatalf("%+v", sel.LastDecision)
	}
}

func TestScoringSelectorCapacityReservation(t *testing.T) {
	var aHits, bHits atomic.Int32
	a := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		aHits.Add(1)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(a.Close)
	b := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		bHits.Add(1)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(b.Close)
	sa := scoringSig("a", 1)
	sa.LatencyMS = 10
	sb := scoringSig("b", 2)
	sb.Health = "degraded"
	sb.LatencyMS = 400
	sel := &ScoringSelector{
		Request: qualify.Request{BuyerOwnerID: "buyer-1", ProjectMode: "shared"},
		Candidates: []qualify.Candidate{
			scoringCand("a", "seller-a", "shared"),
			scoringCand("b", "seller-b", "shared"),
		},
		Signals:   map[string]score.Signals{"a": sa, "b": sb},
		Policy:    score.Policy{Version: "pol-1"},
		Upstreams: map[string]Upstream{"a": {BaseURL: a.URL, Credential: "k"}, "b": {BaseURL: b.URL, Credential: "k"}},
	}
	ctx := context.Background()
	first, err := sel.Select(ctx, "openai", "openai.post.v1.chat.completions")
	if err != nil || first.ConnectionID != "a" {
		t.Fatalf("first %+v %v", first, err)
	}
	second, err := sel.Select(ctx, "openai", "openai.post.v1.chat.completions")
	if err != nil || second.ConnectionID != "b" {
		t.Fatalf("second %+v %v", second, err)
	}
	third, err := sel.Select(ctx, "openai", "openai.post.v1.chat.completions")
	if err != nil || third.ConnectionID != "b" {
		t.Fatalf("third %+v %v", third, err)
	}
	if _, err := sel.Select(ctx, "openai", "openai.post.v1.chat.completions"); err == nil {
		t.Fatal("expected NO_UPSTREAM after remaining exhausted")
	}
	k := &Kernel{Catalog: testCatalog(), Selector: sel}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", rec.Code)
	}
	if aHits.Load() != 0 || bHits.Load() != 0 {
		t.Fatalf("exhausted still forwarded a=%d b=%d", aHits.Load(), bHits.Load())
	}
}

func TestScoringSelectorPolicyLockSnapshot(t *testing.T) {
	sel := &ScoringSelector{
		Request:    qualify.Request{BuyerOwnerID: "buyer-1", ProjectMode: "shared"},
		Candidates: []qualify.Candidate{scoringCand("a", "seller-a", "shared")},
		Signals:    map[string]score.Signals{"a": scoringSig("a", 4)},
		Policy:     score.Policy{Version: "pol-1"},
		Seed:       7,
		Upstreams:  map[string]Upstream{"a": {BaseURL: "http://127.0.0.1:9", Credential: "k"}},
	}
	up, err := sel.Select(context.Background(), "openai", "openai.post.v1.chat.completions")
	if err != nil || up.ConnectionID != "a" {
		t.Fatalf("%+v %v", up, err)
	}
	locked := sel.LastDecision
	sel.Policy = score.Policy{Version: "pol-2", WeightPrice: 99}
	if locked.PolicyVersion != "pol-1" || locked.Seed != 7 {
		t.Fatalf("snapshot mutated %+v", locked)
	}
	up2, err := sel.Select(context.Background(), "openai", "openai.post.v1.chat.completions")
	if err != nil || up2.ConnectionID != "a" {
		t.Fatal(err)
	}
	if sel.LastDecision.PolicyVersion != "pol-2" {
		t.Fatalf("new request %s", sel.LastDecision.PolicyVersion)
	}
}

func TestScoringSelectorSelectConnection(t *testing.T) {
	sel := &ScoringSelector{
		Upstreams: map[string]Upstream{"pin": {BaseURL: "http://up", Credential: "k"}},
	}
	up, err := sel.SelectConnection(context.Background(), "pin")
	if err != nil || up.ConnectionID != "pin" {
		t.Fatalf("%+v %v", up, err)
	}
	if _, err := sel.SelectConnection(context.Background(), "missing"); err == nil {
		t.Fatal("expected miss")
	}
}

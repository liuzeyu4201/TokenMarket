package passthrough

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
)

func TestDedicatedSelectorFailClosedNeverHitsShared(t *testing.T) {
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
	_ = shr
	sel := NewDedicatedSelector(DedicatedSnapshot{
		ConnectionID: "bound",
		Status:       "degraded",
		Health:       "unhealthy",
		Up:           Upstream{BaseURL: ded.URL, Credential: "ded-secret"},
	})
	k := &Kernel{Catalog: testCatalog(), Selector: sel}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), CodeDedicatedUnavailable) {
		t.Fatalf("body %s", rec.Body.String())
	}
	if dedicatedHits.Load() != 0 || sharedHits.Load() != 0 {
		t.Fatalf("hits dedicated=%d shared=%d", dedicatedHits.Load(), sharedHits.Load())
	}
}

func TestDedicatedSelectorActivePinsConnection(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(up.Close)
	sel := NewDedicatedSelector(DedicatedSnapshot{
		ConnectionID: "bound",
		Status:       "active",
		Health:       "healthy",
		Up:           Upstream{BaseURL: up.URL, Credential: "k", ConnectionID: "bound"},
	})
	k := &Kernel{Catalog: testCatalog(), Selector: sel}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"m":1}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
}

func TestDedicatedSelectorOldResourceStaysOnDraining(t *testing.T) {
	sel := NewDedicatedSelector(DedicatedSnapshot{
		ConnectionID: "new",
		Status:       "active",
		Health:       "healthy",
		Up:           Upstream{BaseURL: "http://new", Credential: "new-secret"},
		Draining: map[string]Upstream{
			"old": {BaseURL: "http://old", Credential: "old-secret"},
		},
	})
	got, err := sel.SelectConnection(context.Background(), "old")
	if err != nil || got.ConnectionID != "old" || got.Credential != "old-secret" {
		t.Fatalf("%+v %v", got, err)
	}
	fresh, err := sel.Select(context.Background(), "openai", "ep")
	if err != nil || fresh.ConnectionID != "new" || fresh.Credential != "new-secret" {
		t.Fatalf("%+v %v", fresh, err)
	}
	if _, err := sel.SelectConnection(context.Background(), "other"); err == nil {
		t.Fatal("expected dedicated unavailable")
	}
}

func TestDedicatedSelectorAtomicReplaceNoMixedCredentials(t *testing.T) {
	oldSnap := DedicatedSnapshot{
		ConnectionID: "old",
		Status:       "active",
		Health:       "healthy",
		Up:           Upstream{BaseURL: "http://old", Credential: "old-secret"},
	}
	newSnap := DedicatedSnapshot{
		ConnectionID: "new",
		Status:       "active",
		Health:       "healthy",
		Up:           Upstream{BaseURL: "http://new", Credential: "new-secret"},
		Draining: map[string]Upstream{
			"old": {BaseURL: "http://old", Credential: "old-secret"},
		},
	}
	sel := NewDedicatedSelector(oldSnap)
	var mixed atomic.Int32
	var wg sync.WaitGroup
	ctx := context.Background()
	for i := 0; i < 64; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			up, err := sel.Select(ctx, "openai", "ep")
			if err != nil {
				return
			}
			if up.ConnectionID == "old" && up.Credential != "old-secret" {
				mixed.Add(1)
			}
			if up.ConnectionID == "new" && up.Credential != "new-secret" {
				mixed.Add(1)
			}
			if up.ConnectionID != "old" && up.ConnectionID != "new" {
				mixed.Add(1)
			}
		}()
	}
	sel.Replace(newSnap)
	wg.Wait()
	if mixed.Load() != 0 {
		t.Fatalf("mixed snapshots %d", mixed.Load())
	}
	up, err := sel.Select(ctx, "openai", "ep")
	if err != nil || up.ConnectionID != "new" {
		t.Fatalf("%+v %v", up, err)
	}
}

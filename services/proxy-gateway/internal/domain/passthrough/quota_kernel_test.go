package passthrough

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
)

type recordingQuota struct {
	fail    bool
	reserve atomic.Int32
	abort   atomic.Int32
}

func (q *recordingQuota) Reserve(context.Context, string, string, string, int64) error {
	q.reserve.Add(1)
	if q.fail {
		return ErrInsufficientQuota
	}
	return nil
}

func (q *recordingQuota) Abort(context.Context, string) error {
	q.abort.Add(1)
	return nil
}

func TestQuotaReserveFailClosedDoesNotHitUpstream(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	q := &recordingQuota{fail: true}
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}},
		Quota:    q,
	}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	req.Header.Set("X-Request-ID", "rq-1")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusConflict {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), CodeInsufficientQuota) {
		t.Fatalf("body %s", rec.Body.String())
	}
	if n.Load() != 0 {
		t.Fatal("upstream called")
	}
	if q.reserve.Load() != 1 {
		t.Fatalf("reserve %d", q.reserve.Load())
	}
}

func TestQuotaReserveOnForwardDoesNotAbort(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(up.Close)
	q := &recordingQuota{}
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}},
		Quota:    q,
	}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"m":1}`))
	req.Header.Set("X-Request-ID", "rq-ok")
	req.Header.Set("X-TokenMarket-Reserve-Minor", "25")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if q.reserve.Load() != 1 || q.abort.Load() != 0 || n.Load() != 1 {
		t.Fatalf("reserve=%d abort=%d up=%d", q.reserve.Load(), q.abort.Load(), n.Load())
	}
}

func TestQuotaAbortWhenUpstreamNeverReached(t *testing.T) {
	q := &recordingQuota{}
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: "not-a-url", Credential: "k"}},
		Quota:    q,
	}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status %d", rec.Code)
	}
	if q.reserve.Load() != 0 {
		t.Fatalf("reserve before valid upstream %d", q.reserve.Load())
	}
}

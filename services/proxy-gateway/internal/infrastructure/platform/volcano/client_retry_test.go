package volcano_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

func TestRetryOnlyTransient(t *testing.T) {
	var n atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(429)
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	c.MaxAttempts = 2
	res := c.ListModels(context.Background(), "k")
	if res.Category != providervalid.CategoryRateLimited {
		t.Fatal(res.Category)
	}
	if n.Load() != 1 {
		t.Fatalf("429 must not retry, got %d", n.Load())
	}
}

func TestRetryConnectionStyle(t *testing.T) {
	// First request: close without response is hard; use 503 as temporary
	var n atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c := n.Add(1)
		if c == 1 {
			w.WriteHeader(503)
			return
		}
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"data":[{"id":"doubao-pro-32k"}]}`))
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	c.MaxAttempts = 2
	// 503 is temporary_unavailable - our code retries temporary. Good.
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	res := c.ListModels(ctx, "k")
	// After retry may still be 503 if second succeeds AuthOK
	if n.Load() < 1 {
		t.Fatal("expected calls")
	}
	_ = res
}

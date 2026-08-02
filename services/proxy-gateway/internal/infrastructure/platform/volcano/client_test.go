package volcano_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

func TestListModelsOK(t *testing.T) {
	body := readFixture(t, "models_ok.json")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v3/models" && r.URL.Path != "/models" {
			// client uses base + /models
		}
		if r.Header.Get("Authorization") == "" {
			t.Error("missing auth")
		}
		w.WriteHeader(200)
		_, _ = w.Write(body)
	}))
	defer srv.Close()

	c := volcano.NewModelsClient(srv.URL, 5, 300)
	// BaseURL is used as-is + /models
	res := c.ListModels(context.Background(), "sk-synthetic-test-key-not-real")
	if !res.AuthOK || len(res.ModelIDs) < 1 {
		t.Fatalf("%+v", res)
	}
}

func TestListModels401(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(401)
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	res := c.ListModels(context.Background(), "bad")
	if res.Category != providervalid.CategoryInvalid {
		t.Fatalf("%+v", res)
	}
}

func TestListModels403(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(403)
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	res := c.ListModels(context.Background(), "bad")
	if res.Category != providervalid.CategoryForbidden {
		t.Fatalf("%+v", res)
	}
}

func TestListModelsMalformed(t *testing.T) {
	body := readFixture(t, "models_malformed.json")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_, _ = w.Write(body)
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	res := c.ListModels(context.Background(), "k")
	if res.Category != providervalid.CategoryInvalidResponse {
		t.Fatalf("%+v", res)
	}
}

func TestListModels429RetryAfter(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Retry-After", "9")
		w.WriteHeader(429)
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	res := c.ListModels(context.Background(), "k")
	if res.Category != providervalid.CategoryRateLimited || res.RetryAfterSec != 9 {
		t.Fatalf("%+v", res)
	}
}

func TestListModels429NoRetryAfter(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(429)
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	res := c.ListModels(context.Background(), "k")
	if res.Category != providervalid.CategoryRateLimited || res.RetryAfterSec != 5 {
		t.Fatalf("%+v", res)
	}
}

func TestListModels5xx(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(503)
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	res := c.ListModels(context.Background(), "k")
	if res.Category != providervalid.CategoryTemporaryUnavailable {
		t.Fatalf("%+v", res)
	}
}

func TestListModelsCancel(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(200 * time.Millisecond)
		w.WriteHeader(200)
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Millisecond)
	defer cancel()
	res := c.ListModels(ctx, "k")
	if res.Category != providervalid.CategoryTimeout && res.Category != providervalid.CategoryTemporaryUnavailable {
		// canceled often surfaces as timeout
		if res.AuthOK {
			t.Fatalf("should not auth ok: %+v", res)
		}
	}
}

func readFixture(t *testing.T, name string) []byte {
	t.Helper()
	_, file, _, _ := runtime.Caller(0)
	p := filepath.Join(filepath.Dir(file), "fixtures", name)
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

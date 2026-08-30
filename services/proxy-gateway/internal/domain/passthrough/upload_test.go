package passthrough

import (
	"bytes"
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

func fileUploadCatalog() *endpcatalog.Catalog {
	return &endpcatalog.Catalog{
		CatalogMajor: 1,
		Providers:    []string{"openai", "anthropic", "vertex"},
		Records: []endpcatalog.EndpointRecord{
			{
				ID:           "openai.post.v1.files",
				Provider:     "openai",
				Method:       "POST",
				PathTemplate: "/v1/files",
				Stability:    "stable",
				Stateful:     true,
				Transport:    "multipart",
				Affinity:     "resource_id",
			},
		},
	}
}

func TestMultipartOversizedNotFullyForwarded(t *testing.T) {
	var got atomic.Int64
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n, _ := io.Copy(io.Discard, r.Body)
		got.Store(n)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	k := &Kernel{
		Catalog:  fileUploadCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k", ConnectionID: "conn-A"}},
		Limits:   Limits{MaxRequestBytes: 32, UploadTimeout: time.Second},
	}
	body := strings.Repeat("a", 256)
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/files", strings.NewReader(body))
	req.Header.Set("Content-Type", "multipart/form-data; boundary=x")
	req.ContentLength = int64(len(body))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Fatalf("status %d body %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), CodeTooLarge) {
		t.Fatalf("body %s", rec.Body.String())
	}
	if got.Load() != 0 {
		t.Fatalf("upstream received %d bytes", got.Load())
	}
}

func TestChunkedOversizedTruncated(t *testing.T) {
	var got atomic.Int64
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n, _ := io.Copy(io.Discard, r.Body)
		got.Store(n)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	k := &Kernel{
		Catalog:  fileUploadCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k", ConnectionID: "conn-A"}},
		Limits:   Limits{MaxRequestBytes: 32, UploadTimeout: time.Second},
	}
	payload := bytes.Repeat([]byte("b"), 200)
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/files", bytes.NewReader(payload))
	req.Header.Set("Content-Type", "multipart/form-data; boundary=x")
	req.ContentLength = -1
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code < 400 {
		t.Fatalf("status %d body %s", rec.Code, rec.Body.String())
	}
	if got.Load() >= int64(len(payload)) {
		t.Fatalf("full body forwarded (%d)", got.Load())
	}
}

func TestNoCreateTempInPassthroughAndAffinity(t *testing.T) {
	roots := []string{".", "../affinity"}
	needles := [][]byte{[]byte("os.CreateTemp"), []byte("ioutil.TempFile")}
	for _, root := range roots {
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
			for _, n := range needles {
				if bytes.Contains(b, n) {
					t.Errorf("%s contains %s", path, n)
				}
			}
			return nil
		})
		if err != nil {
			t.Fatal(err)
		}
	}
}

package passthrough

import (
	"context"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/affinity"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

func affinityCatalog() *endpcatalog.Catalog {
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
			{
				ID:           "openai.get.v1.files.file_id",
				Provider:     "openai",
				Method:       "GET",
				PathTemplate: "/v1/files/{file_id}",
				Stability:    "stable",
				Stateful:     true,
				Transport:    "http",
				Affinity:     "resource_id",
			},
			{
				ID:           "openai.delete.v1.files.file_id",
				Provider:     "openai",
				Method:       "DELETE",
				PathTemplate: "/v1/files/{file_id}",
				Stability:    "stable",
				Stateful:     true,
				Transport:    "http",
				Affinity:     "resource_id",
			},
		},
	}
}

type recordSelector struct {
	up      Upstream
	selects atomic.Int32
	pins    atomic.Int32
	lastPin atomic.Value
}

func (s *recordSelector) Select(context.Context, string, string) (Upstream, error) {
	s.selects.Add(1)
	return s.up, nil
}

func (s *recordSelector) SelectConnection(_ context.Context, id string) (Upstream, error) {
	s.pins.Add(1)
	s.lastPin.Store(id)
	if s.up.ConnectionID != "" && s.up.ConnectionID != id {
		return Upstream{}, errNoUpstream
	}
	return s.up, nil
}

func TestCreateThenGetPinsSameConnection(t *testing.T) {
	var sawPath string
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		sawPath = r.URL.Path
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		if r.Method == http.MethodPost {
			_, _ = w.Write([]byte(`{"id":"file-1","object":"file"}`))
			return
		}
		_, _ = w.Write([]byte(`{"id":"file-1","status":"ok"}`))
	}))
	t.Cleanup(up.Close)
	sel := &recordSelector{up: Upstream{BaseURL: up.URL, Credential: "k", ConnectionID: "conn-A"}}
	k := &Kernel{
		Catalog:  affinityCatalog(),
		Selector: sel,
		Affinity: affinity.NewTable(""),
	}
	post := httptest.NewRequest(http.MethodPost, "/openai/v1/files", strings.NewReader("filebytes"))
	post.Header.Set("Content-Type", "multipart/form-data; boundary=x")
	postRec := httptest.NewRecorder()
	k.ServeHTTP(postRec, post, "dedicated", false)
	if postRec.Code != 200 {
		t.Fatalf("create %d %s", postRec.Code, postRec.Body.String())
	}
	if !strings.Contains(postRec.Body.String(), "file-1") {
		t.Fatalf("create body %s", postRec.Body.String())
	}
	if sel.selects.Load() != 1 {
		t.Fatalf("create selects %d", sel.selects.Load())
	}
	get := httptest.NewRequest(http.MethodGet, "/openai/v1/files/file-1", nil)
	getRec := httptest.NewRecorder()
	k.ServeHTTP(getRec, get, "dedicated", false)
	if getRec.Code != 200 {
		t.Fatalf("get %d %s", getRec.Code, getRec.Body.String())
	}
	if sel.pins.Load() != 1 {
		t.Fatalf("pins %d", sel.pins.Load())
	}
	pin, _ := sel.lastPin.Load().(string)
	if pin != "conn-A" {
		t.Fatalf("pinned %q", pin)
	}
	if sel.selects.Load() != 1 {
		t.Fatalf("GET must not Select randomly, selects=%d", sel.selects.Load())
	}
	if sawPath != "/v1/files/file-1" {
		t.Fatalf("path %q", sawPath)
	}
}

func TestAffinityMissingFailClosed(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	sel := &recordSelector{up: Upstream{BaseURL: up.URL, Credential: "k", ConnectionID: "conn-B"}}
	k := &Kernel{
		Catalog:  affinityCatalog(),
		Selector: sel,
		Affinity: affinity.NewTable(""),
	}
	req := httptest.NewRequest(http.MethodGet, "/openai/v1/files/missing", nil)
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != http.StatusNotFound {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), CodeAffinityNotFound) {
		t.Fatalf("body %s", rec.Body.String())
	}
	if sel.selects.Load() != 0 || sel.pins.Load() != 0 {
		t.Fatalf("selector used selects=%d pins=%d", sel.selects.Load(), sel.pins.Load())
	}
	if n.Load() != 0 {
		t.Fatal("missing affinity still forwarded")
	}
}

func TestAffinitySnapshotPinsAfterRestart(t *testing.T) {
	dir := t.TempDir()
	snap := filepath.Join(dir, "affinity.json")
	table := affinity.NewTable(snap)
	if err := table.Put(affinity.Binding{Protocol: "openai", ResourceID: "file-1", ConnectionID: "conn-A"}); err != nil {
		t.Fatal(err)
	}
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"id":"file-1"}`))
	}))
	t.Cleanup(up.Close)
	reloaded := affinity.NewTable(snap)
	sel := &recordSelector{up: Upstream{BaseURL: up.URL, Credential: "k", ConnectionID: "conn-A"}}
	k := &Kernel{Catalog: affinityCatalog(), Selector: sel, Affinity: reloaded}
	req := httptest.NewRequest(http.MethodGet, "/openai/v1/files/file-1", nil)
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != 200 {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
	pin, _ := sel.lastPin.Load().(string)
	if pin != "conn-A" {
		t.Fatalf("pinned %q", pin)
	}
}

func TestAffinityNilTableFailClosed(t *testing.T) {
	sel := &recordSelector{up: Upstream{BaseURL: "http://127.0.0.1:9", Credential: "k", ConnectionID: "conn-A"}}
	k := &Kernel{Catalog: affinityCatalog(), Selector: sel}
	req := httptest.NewRequest(http.MethodGet, "/openai/v1/files/file-1", nil)
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != http.StatusNotFound || !strings.Contains(rec.Body.String(), CodeAffinityNotFound) {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if sel.selects.Load() != 0 {
		t.Fatal("nil table must not select")
	}
}

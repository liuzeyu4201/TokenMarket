package passthrough

import (
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/affinity"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

func vertexStableRecords(t *testing.T) []endpcatalog.EndpointRecord {
	t.Helper()
	cat, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	var out []endpcatalog.EndpointRecord
	for _, rec := range cat.Records {
		if rec.Provider == ProtocolVertex && rec.Stability == "stable" {
			out = append(out, rec)
		}
	}
	if len(out) == 0 {
		t.Fatal("no vertex stable records")
	}
	return out
}

func TestVertexStableCatalogContractTable(t *testing.T) {
	records := vertexStableRecords(t)
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		id := "echo"
		if i := strings.LastIndex(r.URL.Path, "/"); i >= 0 && i+1 < len(r.URL.Path) {
			id = r.URL.Path[i+1:]
		}
		_, _ = w.Write([]byte(`{"id":"` + id + `","echo_path":"` + r.URL.Path + `","echo_method":"` + r.Method + `","echo_body":` + jsonRaw(body) + `}`))
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	table := affinity.NewTable("")
	k := &Kernel{
		Catalog:  cat,
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "tok", ConnectionID: "conn-vtx"}},
		Affinity: table,
	}
	tested := 0
	for _, rec := range records {
		rec := rec
		t.Run(rec.ID, func(t *testing.T) {
			path := instantiatePath(rec.PathTemplate)
			if rec.Affinity == "resource_id" {
				if rid := endpcatalog.ResourceID(endpcatalog.PathVars(rec.PathTemplate, path)); rid != "" {
					if err := table.Put(affinity.Binding{Protocol: ProtocolVertex, ResourceID: rid, ConnectionID: "conn-vtx", EndpointID: rec.ID}); err != nil {
						t.Fatal(err)
					}
				}
			}
			var body io.Reader
			if rec.Method != http.MethodGet && rec.Method != http.MethodDelete {
				body = strings.NewReader(`{"contents":[{"role":"user","parts":[{"text":"hi"}]}],"custom_extra":true}`)
			}
			req := httptest.NewRequest(rec.Method, "/vertex"+path, body)
			if body != nil {
				req.Header.Set("Content-Type", "application/json")
			}
			recw := httptest.NewRecorder()
			k.ServeHTTP(recw, req, "dedicated", false)
			if recw.Code != 200 {
				t.Fatalf("status %d body %s", recw.Code, recw.Body.String())
			}
			if !strings.Contains(recw.Body.String(), `"echo_path":"`+path+`"`) {
				t.Fatalf("path not echoed: %s", recw.Body.String())
			}
			tested++
		})
	}
	if tested != len(records) {
		t.Fatalf("coverage %d/%d", tested, len(records))
	}
}

func TestVertexGeneratePreservesProjectLocationAndJSON(t *testing.T) {
	var gotPath, gotBody string
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		b, _ := io.ReadAll(r.Body)
		gotBody = string(b)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"candidates":[{"content":{"role":"model","parts":[{"text":"ok"}]}}],"usageMetadata":{"totalTokenCount":3}}`))
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "tok"}}}
	path := "/vertex/v1/projects/buyer-proj/locations/us-central1/publishers/google/models/gemini-1.5-pro:generateContent"
	body := `{"contents":[{"role":"user","parts":[{"text":"hi"}]}],"custom_extra":{"keep":true}}`
	req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if gotPath != "/v1/projects/buyer-proj/locations/us-central1/publishers/google/models/gemini-1.5-pro:generateContent" {
		t.Fatalf("path rewritten %q", gotPath)
	}
	if gotBody != body {
		t.Fatalf("body mutated %s", gotBody)
	}
	if strings.Contains(rec.Body.String(), `"choices"`) {
		t.Fatal("openai rewrite")
	}
}

func TestVertexOperationNamePinsConnection(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		if strings.Contains(r.URL.Path, "predictLongRunning") {
			_, _ = w.Write([]byte(`{"name":"projects/p/locations/us/operations/op-sf21"}`))
			return
		}
		_, _ = w.Write([]byte(`{"name":"projects/p/locations/us/operations/op-sf21","done":true}`))
	}))
	t.Cleanup(up.Close)
	sel := &recordSelector{up: Upstream{BaseURL: up.URL, Credential: "tok", ConnectionID: "conn-A"}}
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: sel, Affinity: affinity.NewTable("")}
	post := httptest.NewRequest(http.MethodPost, "/vertex/v1/projects/p/locations/us/publishers/google/models/m:predictLongRunning", strings.NewReader(`{}`))
	postRec := httptest.NewRecorder()
	k.ServeHTTP(postRec, post, "dedicated", false)
	if postRec.Code != 200 {
		t.Fatalf("create %d %s", postRec.Code, postRec.Body.String())
	}
	get := httptest.NewRequest(http.MethodGet, "/vertex/v1/projects/p/locations/us/operations/op-sf21", nil)
	getRec := httptest.NewRecorder()
	k.ServeHTTP(getRec, get, "dedicated", false)
	if getRec.Code != 200 {
		t.Fatalf("get %d %s", getRec.Code, getRec.Body.String())
	}
	pin, _ := sel.lastPin.Load().(string)
	if pin != "conn-A" {
		t.Fatalf("pin %q selects=%d pins=%d", pin, sel.selects.Load(), sel.pins.Load())
	}
}

func TestVertexStatefulSharedRejected(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "tok"}}}
	req := httptest.NewRequest(http.MethodPost, "/vertex/v1/projects/p/locations/us/batchPredictionJobs", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusForbidden || !strings.Contains(rec.Body.String(), endpcatalog.CodeDedicatedRequired) {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if n.Load() != 0 {
		t.Fatal("forwarded")
	}
}

func TestVertexControlPlaneNotGoogleRPC(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "tok"}}}
	count := 0
	for _, rec := range cat.Records {
		if rec.Provider != ProtocolVertex || rec.Stability != "control_plane" {
			continue
		}
		count++
		path := instantiatePath(rec.PathTemplate)
		req := httptest.NewRequest(rec.Method, "/vertex"+path, strings.NewReader(`{}`))
		recw := httptest.NewRecorder()
		k.ServeHTTP(recw, req, "dedicated", false)
		if recw.Code != http.StatusForbidden || !strings.Contains(recw.Body.String(), endpcatalog.CodeControlPlane) {
			t.Fatalf("%s %d %s", rec.ID, recw.Code, recw.Body.String())
		}
		if strings.Contains(recw.Body.String(), "google.rpc") || strings.Contains(recw.Body.String(), `"status"`) && strings.Contains(recw.Body.String(), `"code":`) && strings.Contains(recw.Body.String(), "google") {
			if strings.Contains(recw.Body.String(), "google.rpc.Status") {
				t.Fatalf("google.rpc disguise %s", recw.Body.String())
			}
		}
	}
	if count == 0 || n.Load() != 0 {
		t.Fatalf("count=%d forwarded=%d", count, n.Load())
	}
}

func TestVertexPreviewRequiresOptIn(t *testing.T) {
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: FailClosedSelector{}}
	req := httptest.NewRequest(http.MethodPost, "/vertex/v1beta1/projects/p/locations/us/publishers/google/models/m:generateContent", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != http.StatusForbidden || !strings.Contains(rec.Body.String(), endpcatalog.CodePreview) {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
}

func TestVertexUncatalogedPlatformEnvelope(t *testing.T) {
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: FailClosedSelector{}}
	req := httptest.NewRequest(http.MethodPost, "/vertex/v1/not-cataloged", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != http.StatusNotFound || !strings.Contains(rec.Body.String(), endpcatalog.CodeNotCataloged) {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if strings.Contains(rec.Body.String(), "google.rpc.Status") {
		t.Fatal("disguised as google.rpc")
	}
}

func TestVertexLiveSmokeSkippedWithoutEnv(t *testing.T) {
	if os.Getenv("TOKENMARKET_VERTEX_SMOKE") != "1" {
		t.Skip("TOKENMARKET_VERTEX_SMOKE not set")
	}
	t.Fatal("live smoke is not authorized in this Goal")
}

package passthrough

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"regexp"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/affinity"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

var pathBrace = regexp.MustCompile(`\{[^{}/]+\}`)

func instantiatePath(tmpl string) string {
	return pathBrace.ReplaceAllStringFunc(tmpl, func(m string) string {
		return "tm-" + m[1:len(m)-1]
	})
}

func openaiStableRecords(t *testing.T) []endpcatalog.EndpointRecord {
	t.Helper()
	cat, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	var out []endpcatalog.EndpointRecord
	for _, rec := range cat.Records {
		if rec.Provider == ProtocolOpenAI && rec.Stability == "stable" {
			out = append(out, rec)
		}
	}
	if len(out) == 0 {
		t.Fatal("no openai stable records")
	}
	return out
}

func TestOpenAIStableCatalogContractTable(t *testing.T) {
	records := openaiStableRecords(t)
	var forwarded atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		forwarded.Add(1)
		body, _ := io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("X-Request-ID", r.Header.Get("X-Request-ID"))
		w.WriteHeader(200)
		id := "echo"
		if i := strings.LastIndex(r.URL.Path, "/"); i >= 0 && i+1 < len(r.URL.Path) {
			id = r.URL.Path[i+1:]
		}
		_, _ = w.Write([]byte(`{"id":"` + id + `","echo_path":"` + r.URL.Path + `","echo_method":"` + r.Method + `","echo_body":` + jsonRaw(body) + `}`))
	}))
	t.Cleanup(up.Close)

	cat, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	table := affinity.NewTable("")
	k := &Kernel{
		Catalog:  cat,
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "sk-up", ConnectionID: "conn-openai"}},
		Affinity: table,
	}

	tested := 0
	for _, rec := range records {
		rec := rec
		t.Run(rec.ID, func(t *testing.T) {
			path := instantiatePath(rec.PathTemplate)
			if rec.Affinity == "resource_id" {
				if rid := endpcatalog.ResourceID(endpcatalog.PathVars(rec.PathTemplate, path)); rid != "" {
					if err := table.Put(affinity.Binding{Protocol: ProtocolOpenAI, ResourceID: rid, ConnectionID: "conn-openai", EndpointID: rec.ID}); err != nil {
						t.Fatal(err)
					}
				}
			}
			method := rec.Method
			var body io.Reader
			if method != http.MethodGet && method != http.MethodDelete && method != "WEBSOCKET" {
				body = strings.NewReader(`{"probe":true,"custom_extra":1}`)
			}
			url := "/openai" + path + "?keep=1"
			if method == "WEBSOCKET" {
				method = http.MethodGet
			}
			req := httptest.NewRequest(method, url, body)
			if rec.Transport == "websocket" {
				req.Header.Set("Upgrade", "websocket")
				req.Header.Set("Connection", "Upgrade")
			}
			if body != nil {
				req.Header.Set("Content-Type", "application/json")
			}
			req.Header.Set("X-Request-ID", "rid-"+rec.ID)
			recw := httptest.NewRecorder()
			k.ServeHTTP(recw, req, "dedicated", false)
			if recw.Code != 200 {
				t.Fatalf("status %d body %s", recw.Code, recw.Body.String())
			}
			if !strings.Contains(recw.Body.String(), `"echo_path":"`+path+`"`) {
				t.Fatalf("path not echoed: %s", recw.Body.String())
			}
			if rec.Transport != "websocket" && !strings.Contains(recw.Body.String(), `"echo_method":"`+rec.Method+`"`) {
				t.Fatalf("method not echoed: %s", recw.Body.String())
			}
			tested++
		})
	}
	if tested != len(records) {
		t.Fatalf("coverage %d/%d", tested, len(records))
	}
}

func jsonRaw(b []byte) string {
	if len(b) == 0 {
		return `""`
	}
	if json.Valid(b) {
		return string(b)
	}
	enc, _ := json.Marshal(string(b))
	return string(enc)
}

func TestOpenAIUnknownJSONAndQueryPreserved(t *testing.T) {
	var got string
	var query string
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		got = string(b)
		query = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"id":"chatcmpl-x","usage":{"total_tokens":3},"custom_echo":true}`))
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "sk-up"}}}
	body := `{"model":"gpt-test","messages":[{"role":"user","content":"hi"}],"custom_extra":{"keep":true}}`
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions?foo=bar", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if got != body {
		t.Fatalf("body mutated %s", got)
	}
	if query != "foo=bar" {
		t.Fatalf("query %q", query)
	}
	if !strings.Contains(rec.Body.String(), `"custom_echo":true`) || !strings.Contains(rec.Body.String(), `"total_tokens":3`) {
		t.Fatalf("response mutated %s", rec.Body.String())
	}
}

func TestOpenAIUpstreamErrorShapeUnchanged(t *testing.T) {
	native := `{"error":{"message":"bad","type":"invalid_request_error","code":"x"}}`
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(400)
		_, _ = w.Write([]byte(native))
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "sk-up"}}}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/embeddings", strings.NewReader(`{"model":"t","input":"h"}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != 400 || rec.Body.String() != native {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
}

func TestOpenAIStatefulSharedRejected(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}}}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/files", strings.NewReader("x"))
	req.Header.Set("Content-Type", "multipart/form-data; boundary=x")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusForbidden || !strings.Contains(rec.Body.String(), endpcatalog.CodeDedicatedRequired) {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if n.Load() != 0 {
		t.Fatal("forwarded stateful shared")
	}
}

func TestOpenAIFileLifecyclePinsConnection(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		if r.Method == http.MethodPost {
			_, _ = w.Write([]byte(`{"id":"file-sf19","object":"file"}`))
			return
		}
		_, _ = w.Write([]byte(`{"id":"file-sf19","ok":true}`))
	}))
	t.Cleanup(up.Close)
	sel := &recordSelector{up: Upstream{BaseURL: up.URL, Credential: "k", ConnectionID: "conn-A"}}
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: sel, Affinity: affinity.NewTable("")}
	post := httptest.NewRequest(http.MethodPost, "/openai/v1/files", strings.NewReader("bytes"))
	post.Header.Set("Content-Type", "multipart/form-data; boundary=x")
	postRec := httptest.NewRecorder()
	k.ServeHTTP(postRec, post, "dedicated", false)
	if postRec.Code != 200 {
		t.Fatalf("create %d %s", postRec.Code, postRec.Body.String())
	}
	get := httptest.NewRequest(http.MethodGet, "/openai/v1/files/file-sf19", nil)
	getRec := httptest.NewRecorder()
	k.ServeHTTP(getRec, get, "dedicated", false)
	if getRec.Code != 200 {
		t.Fatalf("get %d %s", getRec.Code, getRec.Body.String())
	}
	pin, _ := sel.lastPin.Load().(string)
	if pin != "conn-A" || sel.selects.Load() != 1 {
		t.Fatalf("pin=%q selects=%d pins=%d", pin, sel.selects.Load(), sel.pins.Load())
	}
}

func TestOpenAIRealtimeCatalogAdmitted(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.EqualFold(r.Header.Get("Upgrade"), "websocket") {
			http.Error(w, "no upgrade", 400)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k", ConnectionID: "conn-ws"}}}
	req := httptest.NewRequest(http.MethodGet, "/openai/v1/realtime", nil)
	req.Header.Set("Upgrade", "websocket")
	req.Header.Set("Connection", "Upgrade")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
}

func TestOpenAIControlPlaneNoneForwarded(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	cat, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}}}
	count := 0
	for _, rec := range cat.Records {
		if rec.Provider != ProtocolOpenAI || rec.Stability != "control_plane" {
			continue
		}
		count++
		path := instantiatePath(rec.PathTemplate)
		req := httptest.NewRequest(rec.Method, "/openai"+path, nil)
		recw := httptest.NewRecorder()
		k.ServeHTTP(recw, req, "dedicated", false)
		if recw.Code != http.StatusForbidden || !strings.Contains(recw.Body.String(), endpcatalog.CodeControlPlane) {
			t.Fatalf("%s %d %s", rec.ID, recw.Code, recw.Body.String())
		}
	}
	if count == 0 {
		t.Fatal("no control plane records")
	}
	if n.Load() != 0 {
		t.Fatalf("forwarded %d control-plane requests", n.Load())
	}
}

func TestOpenAIUncataloged(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}}}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/not-a-cataloged-endpoint", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != http.StatusNotFound || !strings.Contains(rec.Body.String(), endpcatalog.CodeNotCataloged) {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if n.Load() != 0 {
		t.Fatal("uncataloged forwarded")
	}
}

func TestOpenAIPreviewRequiresOptIn(t *testing.T) {
	cat, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	var rec *endpcatalog.EndpointRecord
	for i := range cat.Records {
		r := &cat.Records[i]
		if r.Provider == ProtocolOpenAI && (r.Stability == "preview" || r.Stability == "beta") {
			rec = r
			break
		}
	}
	if rec == nil {
		t.Skip("no openai preview records")
	}
	k := &Kernel{Catalog: cat, Selector: FailClosedSelector{}}
	path := instantiatePath(rec.PathTemplate)
	req := httptest.NewRequest(rec.Method, "/openai"+path, strings.NewReader(`{}`))
	if rec.Method == "WEBSOCKET" {
		req = httptest.NewRequest(http.MethodGet, "/openai"+path, nil)
		req.Header.Set("Upgrade", "websocket")
		req.Header.Set("Connection", "Upgrade")
	}
	out := httptest.NewRecorder()
	k.ServeHTTP(out, req, "dedicated", false)
	if out.Code != http.StatusForbidden || !strings.Contains(out.Body.String(), endpcatalog.CodePreview) {
		t.Fatalf("%d %s", out.Code, out.Body.String())
	}
}

func TestOpenAILiveSmokeSkippedWithoutEnv(t *testing.T) {
	if os.Getenv("TOKENMARKET_OPENAI_SMOKE") != "1" {
		t.Skip("TOKENMARKET_OPENAI_SMOKE not set; paid live smoke is a release blocker")
	}
	t.Fatal("live smoke is not authorized in this Goal")
}

func TestOpenAIStableCoverageReport(t *testing.T) {
	cat, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	var stable, control, preview int
	for _, rec := range cat.Records {
		if rec.Provider != ProtocolOpenAI {
			continue
		}
		switch rec.Stability {
		case "stable":
			stable++
		case "control_plane":
			control++
		case "preview", "beta":
			preview++
		}
	}
	if stable < 1 || control < 1 {
		t.Fatalf("stable=%d control=%d preview=%d", stable, control, preview)
	}
	t.Logf("openai catalog coverage denominator stable=%d control_plane=%d preview_or_beta=%d", stable, control, preview)
}

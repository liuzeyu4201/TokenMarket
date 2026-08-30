package passthrough

import (
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/affinity"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

func anthropicStableRecords(t *testing.T) []endpcatalog.EndpointRecord {
	t.Helper()
	cat, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	var out []endpcatalog.EndpointRecord
	for _, rec := range cat.Records {
		if rec.Provider == ProtocolAnthropic && rec.Stability == "stable" {
			out = append(out, rec)
		}
	}
	if len(out) == 0 {
		t.Fatal("no anthropic stable records")
	}
	return out
}

func TestAnthropicStableCatalogContractTable(t *testing.T) {
	records := anthropicStableRecords(t)
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
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "sk-ant", ConnectionID: "conn-ant"}},
		Affinity: table,
	}
	tested := 0
	for _, rec := range records {
		rec := rec
		t.Run(rec.ID, func(t *testing.T) {
			path := instantiatePath(rec.PathTemplate)
			if rec.Affinity == "resource_id" {
				if rid := endpcatalog.ResourceID(endpcatalog.PathVars(rec.PathTemplate, path)); rid != "" {
					if err := table.Put(affinity.Binding{Protocol: ProtocolAnthropic, ResourceID: rid, ConnectionID: "conn-ant", EndpointID: rec.ID}); err != nil {
						t.Fatal(err)
					}
				}
			}
			var body io.Reader
			if rec.Method != http.MethodGet && rec.Method != http.MethodDelete {
				body = strings.NewReader(`{"model":"claude-test","max_tokens":16,"custom_extra":true}`)
			}
			req := httptest.NewRequest(rec.Method, "/anthropic"+path, body)
			if body != nil {
				req.Header.Set("Content-Type", "application/json")
			}
			req.Header.Set("anthropic-version", "2023-06-01")
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

func TestAnthropicMessagesNotRewrittenToOpenAI(t *testing.T) {
	var got string
	var version string
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		got = string(b)
		version = r.Header.Get("anthropic-version")
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("request-id", "req_up_1")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"id":"msg_1","type":"message","role":"assistant","content":[{"type":"text","text":"hi"}],"usage":{"input_tokens":1,"output_tokens":1}}`))
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}}}
	body := `{"model":"claude-test","max_tokens":16,"messages":[{"role":"user","content":"hi"}],"custom_extra":1}`
	req := httptest.NewRequest(http.MethodPost, "/anthropic/v1/messages", strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("anthropic-version", "2023-06-01")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != 200 {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if got != body {
		t.Fatalf("body mutated %s", got)
	}
	if version != "2023-06-01" {
		t.Fatalf("anthropic-version dropped %q", version)
	}
	if strings.Contains(rec.Body.String(), `"choices"`) {
		t.Fatal("rewritten to openai choices")
	}
	if !strings.Contains(rec.Body.String(), `"type":"message"`) {
		t.Fatalf("anthropic shape lost %s", rec.Body.String())
	}
}

func TestAnthropicSSEEventOrderUnchanged(t *testing.T) {
	events := []string{
		"event: message_start\ndata: {\"type\":\"message_start\"}\n\n",
		"event: content_block_delta\ndata: {\"type\":\"content_block_delta\"}\n\n",
		"event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n",
	}
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(200)
		fl := w.(http.Flusher)
		for _, e := range events {
			fmt.Fprint(w, e)
			fl.Flush()
		}
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{
		Catalog:  cat,
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}},
		Limits:   Limits{IdleTimeout: time.Second},
	}
	req := httptest.NewRequest(http.MethodPost, "/anthropic/v1/messages", strings.NewReader(`{"model":"c","max_tokens":8,"messages":[]}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	got := rec.Body.String()
	pos := 0
	for _, e := range events {
		i := strings.Index(got[pos:], e)
		if i < 0 {
			t.Fatalf("missing or reordered event %q in %q", e, got)
		}
		pos += i + len(e)
	}
	if strings.Contains(got, "chat.completion.chunk") {
		t.Fatal("openai stream rewrite")
	}
}

func TestAnthropicBatchPinsConnection(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		if r.Method == http.MethodPost && r.URL.Path == "/v1/messages/batches" {
			_, _ = w.Write([]byte(`{"id":"batch-sf20","type":"message_batch"}`))
			return
		}
		_, _ = w.Write([]byte(`{"id":"batch-sf20","processing_status":"ended"}`))
	}))
	t.Cleanup(up.Close)
	sel := &recordSelector{up: Upstream{BaseURL: up.URL, Credential: "k", ConnectionID: "conn-A"}}
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: sel, Affinity: affinity.NewTable("")}
	post := httptest.NewRequest(http.MethodPost, "/anthropic/v1/messages/batches", strings.NewReader(`{"requests":[]}`))
	postRec := httptest.NewRecorder()
	k.ServeHTTP(postRec, post, "dedicated", false)
	if postRec.Code != 200 {
		t.Fatalf("create %d %s", postRec.Code, postRec.Body.String())
	}
	get := httptest.NewRequest(http.MethodGet, "/anthropic/v1/messages/batches/batch-sf20", nil)
	getRec := httptest.NewRecorder()
	k.ServeHTTP(getRec, get, "dedicated", false)
	if getRec.Code != 200 {
		t.Fatalf("get %d %s", getRec.Code, getRec.Body.String())
	}
	pin, _ := sel.lastPin.Load().(string)
	if pin != "conn-A" {
		t.Fatalf("pin %q", pin)
	}
}

func TestAnthropicBatchSharedRejected(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}}}
	req := httptest.NewRequest(http.MethodPost, "/anthropic/v1/messages/batches", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusForbidden || !strings.Contains(rec.Body.String(), endpcatalog.CodeDedicatedRequired) {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
	if n.Load() != 0 {
		t.Fatal("forwarded")
	}
}

func TestAnthropicControlPlaneNoneForwarded(t *testing.T) {
	var n atomic.Int32
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}}}
	count := 0
	for _, rec := range cat.Records {
		if rec.Provider != ProtocolAnthropic || rec.Stability != "control_plane" {
			continue
		}
		count++
		path := instantiatePath(rec.PathTemplate)
		req := httptest.NewRequest(rec.Method, "/anthropic"+path, nil)
		recw := httptest.NewRecorder()
		k.ServeHTTP(recw, req, "dedicated", false)
		if recw.Code != http.StatusForbidden || !strings.Contains(recw.Body.String(), endpcatalog.CodeControlPlane) {
			t.Fatalf("%s %d %s", rec.ID, recw.Code, recw.Body.String())
		}
	}
	if count == 0 || n.Load() != 0 {
		t.Fatalf("count=%d forwarded=%d", count, n.Load())
	}
}

func TestAnthropicBetaFilesRequireOptIn(t *testing.T) {
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: FailClosedSelector{}}
	req := httptest.NewRequest(http.MethodPost, "/anthropic/v1/files", strings.NewReader("x"))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != http.StatusForbidden || !strings.Contains(rec.Body.String(), endpcatalog.CodePreview) {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
}

func TestAnthropicUncataloged(t *testing.T) {
	cat, _ := endpcatalog.LoadEmbedded(1)
	k := &Kernel{Catalog: cat, Selector: FailClosedSelector{}}
	req := httptest.NewRequest(http.MethodPost, "/anthropic/v1/not-cataloged", strings.NewReader(`{}`))
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "dedicated", false)
	if rec.Code != http.StatusNotFound || !strings.Contains(rec.Body.String(), endpcatalog.CodeNotCataloged) {
		t.Fatalf("%d %s", rec.Code, rec.Body.String())
	}
}

func TestAnthropicLiveSmokeSkippedWithoutEnv(t *testing.T) {
	if os.Getenv("TOKENMARKET_ANTHROPIC_SMOKE") != "1" {
		t.Skip("TOKENMARKET_ANTHROPIC_SMOKE not set")
	}
	t.Fatal("live smoke is not authorized in this Goal")
}

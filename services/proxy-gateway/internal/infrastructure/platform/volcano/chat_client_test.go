package volcano_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

func TestPostJSONParsesChoicesAndAllowlistHeaders(t *testing.T) {
	ok, _ := os.ReadFile(filepath.Join(fixtureDir(t), "chat_ok.json"))
	var gotAuth, gotCT, gotAccept string
	var extra []string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/chat/completions" && !strings.HasSuffix(r.URL.Path, "/chat/completions") {
			t.Errorf("path %s", r.URL.Path)
		}
		gotAuth = r.Header.Get("Authorization")
		gotCT = r.Header.Get("Content-Type")
		gotAccept = r.Header.Get("Accept")
		for k := range r.Header {
			lk := strings.ToLower(k)
			if lk == "cookie" || lk == "x-internal-token" {
				extra = append(extra, k)
			}
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write(ok)
	}))
	defer srv.Close()

	c := volcano.NewChatClient(srv.URL)
	res := c.PostJSON(context.Background(), "sk-synthetic-test-key-not-real", []byte(`{"model":"doubao-pro-32k"}`), false)
	if res.Err != nil {
		t.Fatal(res.Err)
	}
	if res.Status != 200 {
		t.Fatal(res.Status)
	}
	var obj map[string]any
	if err := json.Unmarshal(res.Body, &obj); err != nil {
		t.Fatal(err)
	}
	if _, ok := obj["choices"]; !ok {
		t.Fatal("choices")
	}
	if gotAuth != "Bearer sk-synthetic-test-key-not-real" || gotCT != "application/json" || gotAccept != "application/json" {
		t.Fatalf("headers %s %s %s", gotAuth, gotCT, gotAccept)
	}
	if len(extra) > 0 {
		t.Fatalf("leaked %v", extra)
	}
}

func TestPostJSONRejectsBodyOneByteOverCapBeforeJSON(t *testing.T) {
	payload := []byte("xxxxx") // 5 bytes, not JSON
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_, _ = w.Write(payload)
	}))
	defer srv.Close()
	c := volcano.NewChatClient(srv.URL)
	c.MaxResponseBytes = 4
	res := c.PostJSON(context.Background(), "sk-synthetic-test-key-not-real", []byte(`{}`), false)
	if res.Err != volcano.ErrResponseTooLarge {
		t.Fatalf("got %v body=%q", res.Err, res.Body)
	}
	if json.Valid(res.Body) {
		t.Fatal("must not JSON-decode an oversized body")
	}
}

func TestPostJSONDoesNotForwardBuyerHeaders(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Cookie") != "" || r.Header.Get("X-Internal-Token") != "" {
			t.Errorf("forwarded forbidden header")
		}
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"choices":[]}`))
	}))
	defer srv.Close()
	c := volcano.NewChatClient(srv.URL)
	_ = c.PostJSON(context.Background(), "sk-synthetic-test-key-not-real", []byte(`{}`), false)
}

func TestPostStreamAcceptEventStream(t *testing.T) {
	var accept string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		accept = r.Header.Get("Accept")
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = w.Write([]byte("data: {\"i\":1}\n\ndata: [DONE]\n\n"))
	}))
	defer srv.Close()
	c := volcano.NewChatClient(srv.URL)
	resp, err := c.PostStream(context.Background(), "sk-synthetic-test-key-not-real", []byte(`{"stream":true}`))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if accept != "text/event-stream" {
		t.Fatalf("accept %s", accept)
	}
	p := volcano.NewSSEParser(resp.Body)
	ev, err := p.Next()
	if err != nil {
		t.Fatal(err)
	}
	if ev.Data == "" {
		t.Fatal("empty")
	}
}

func TestClassifyCallTransport(t *testing.T) {
	res := volcano.ChatCallResult{Err: context.DeadlineExceeded}
	if volcano.ClassifyCall(res) != chatcompat.CategoryTimeout {
		t.Fatal("timeout")
	}
	res = volcano.ChatCallResult{Status: 429, Body: []byte(`{}`)}
	if volcano.ClassifyCall(res) != chatcompat.CategoryRateLimited {
		t.Fatal("429")
	}
}

func fixtureDir(t *testing.T) string {
	t.Helper()
	_, file, _, _ := runtime.Caller(0)
	return filepath.Join(filepath.Dir(file), "fixtures")
}

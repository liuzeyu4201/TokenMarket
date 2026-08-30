package passthrough

import (
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestTopLevelIDPrefersID(t *testing.T) {
	got := topLevelID([]byte(`{"object":"file","id":"file-1","file_id":"other"}`))
	if got != "file-1" {
		t.Fatalf("%q", got)
	}
}

func TestTopLevelIDFallback(t *testing.T) {
	got := topLevelID([]byte(`{"object":"file","file_id":"file-9"}`))
	if got != "file-9" {
		t.Fatalf("%q", got)
	}
}

func TestTopLevelIDEmpty(t *testing.T) {
	if got := topLevelID([]byte(`not json`)); got != "" {
		t.Fatalf("%q", got)
	}
}

func TestWebsocketUpgradeDetect(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/openai/v1/realtime", nil)
	req.Header.Set("Upgrade", "websocket")
	req.Header.Set("Connection", "Upgrade")
	if !websocketUpgrade(req) {
		t.Fatal("expected upgrade")
	}
	req2 := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader("{}"))
	if websocketUpgrade(req2) {
		t.Fatal("plain POST is not websocket")
	}
}

func TestIDTeeExtractsOnEOF(t *testing.T) {
	var got string
	src := io.NopCloser(strings.NewReader(`{"id":"file-xyz","object":"file"}`))
	tee := newIDTee(src, func(id string) { got = id })
	if _, err := io.ReadAll(tee); err != nil {
		t.Fatal(err)
	}
	if err := tee.Close(); err != nil {
		t.Fatal(err)
	}
	if got != "file-xyz" {
		t.Fatalf("%q", got)
	}
}

func TestDeadlineReadCloserTimeout(t *testing.T) {
	r := &deadlineReadCloser{ReadCloser: io.NopCloser(strings.NewReader("abc")), deadline: time.Now().Add(-time.Second)}
	_, err := r.Read(make([]byte, 1))
	if !errors.Is(err, errUploadTimeout) {
		t.Fatalf("%v", err)
	}
}

func TestStreamWriterUnwrap(t *testing.T) {
	rec := httptest.NewRecorder()
	w := &streamWriter{ResponseWriter: rec}
	if w.Unwrap() != rec {
		t.Fatal("unwrap")
	}
	w.Flush()
}

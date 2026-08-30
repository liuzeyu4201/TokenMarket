package passthrough

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"
)

type streamRecorder struct {
	h    http.Header
	code int
	ch   chan string
	once sync.Once
}

func newStreamRecorder() *streamRecorder {
	return &streamRecorder{h: make(http.Header), ch: make(chan string, 16)}
}

func (s *streamRecorder) Header() http.Header { return s.h }
func (s *streamRecorder) WriteHeader(c int)   { s.code = c }
func (s *streamRecorder) Write(p []byte) (int, error) {
	if s.code == 0 {
		s.code = 200
	}
	cp := string(p)
	s.ch <- cp
	return len(p), nil
}
func (s *streamRecorder) Flush() {}

func TestSSEEventOrderFlushed(t *testing.T) {
	gate := make(chan struct{})
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(200)
		fl := w.(http.Flusher)
		fmt.Fprint(w, "data: a\n\n")
		fl.Flush()
		<-gate
		fmt.Fprint(w, "data: b\n\n")
		fl.Flush()
		fmt.Fprint(w, "data: c\n\n")
		fl.Flush()
	}))
	t.Cleanup(up.Close)
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}},
		Limits:   Limits{IdleTimeout: time.Second, UpstreamTimeout: 5 * time.Second},
	}
	rec := newStreamRecorder()
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
	done := make(chan struct{})
	go func() {
		k.ServeHTTP(rec, req, "shared", false)
		close(done)
	}()
	select {
	case chunk := <-rec.ch:
		if !strings.Contains(chunk, "data: a") {
			t.Fatalf("first flush %q", chunk)
		}
	case <-time.After(time.Second):
		t.Fatal("did not flush event a before stream end")
	}
	close(gate)
	var rest strings.Builder
	timeout := time.After(time.Second)
	for {
		select {
		case chunk := <-rec.ch:
			rest.WriteString(chunk)
			if strings.Contains(rest.String(), "data: b") && strings.Contains(rest.String(), "data: c") {
				<-done
				return
			}
		case <-done:
			if !strings.Contains(rest.String(), "data: b") || !strings.Contains(rest.String(), "data: c") {
				t.Fatalf("missing later events: %s", rest.String())
			}
			return
		case <-timeout:
			t.Fatalf("timeout rest=%s", rest.String())
		}
	}
}

type stallWriter struct {
	h       http.Header
	code    int
	blocked chan struct{}
	release chan struct{}
}

func (s *stallWriter) Header() http.Header {
	if s.h == nil {
		s.h = make(http.Header)
	}
	return s.h
}
func (s *stallWriter) WriteHeader(c int) { s.code = c }
func (s *stallWriter) Write(p []byte) (int, error) {
	select {
	case <-s.blocked:
	default:
		close(s.blocked)
	}
	<-s.release
	return 0, io.ErrClosedPipe
}
func (s *stallWriter) Flush() {}

func TestSSEIdleTimeoutDoesNotBlockOthers(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(200)
		fl := w.(http.Flusher)
		fmt.Fprint(w, "data: a\n\n")
		fl.Flush()
		time.Sleep(400 * time.Millisecond)
		fmt.Fprint(w, "data: b\n\n")
		fl.Flush()
	}))
	t.Cleanup(up.Close)
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}},
		Limits:   Limits{IdleTimeout: 80 * time.Millisecond, UpstreamTimeout: 2 * time.Second},
	}
	stall := &stallWriter{blocked: make(chan struct{}), release: make(chan struct{})}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
	done := make(chan struct{})
	go func() {
		k.ServeHTTP(stall, req, "shared", false)
		close(done)
	}()
	select {
	case <-stall.blocked:
	case <-time.After(time.Second):
		t.Fatal("writer did not block")
	}
	okReq := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
	okRec := httptest.NewRecorder()
	k.ServeHTTP(okRec, okReq, "shared", false)
	if okRec.Code != 200 && !strings.Contains(okRec.Body.String(), "data: a") {
		if okRec.Code >= 500 {
			t.Fatalf("other request failed status %d body %s", okRec.Code, okRec.Body.String())
		}
	}
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("idle timeout did not end stalled stream")
	}
	close(stall.release)
}

func TestSSECancelReachesUpstream(t *testing.T) {
	started := make(chan struct{})
	canceled := make(chan struct{})
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: "http://127.0.0.1:9", Credential: "k"}},
		Limits:   Limits{IdleTimeout: time.Second, UpstreamTimeout: 5 * time.Second},
		Transport: roundTripFunc(func(req *http.Request) (*http.Response, error) {
			close(started)
			select {
			case <-req.Context().Done():
				close(canceled)
				return nil, req.Context().Err()
			case <-time.After(5 * time.Second):
				t.Error("transport did not see cancel")
				return nil, context.DeadlineExceeded
			}
		}),
	}
	ctx, cancel := context.WithCancel(context.Background())
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`)).WithContext(ctx)
	go func() {
		<-started
		cancel()
	}()
	rec := httptest.NewRecorder()
	done := make(chan struct{})
	go func() {
		k.ServeHTTP(rec, req, "shared", false)
		close(done)
	}()
	select {
	case <-canceled:
	case <-time.After(time.Second):
		t.Fatal("cancel not observed within 1s")
	}
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("handler stuck")
	}
}

func TestUpgradeStrippedOnNonWebsocket(t *testing.T) {
	var sawUpgrade string
	k, _, _ := kernelAgainst(t, func(w http.ResponseWriter, r *http.Request) {
		sawUpgrade = r.Header.Get("Upgrade")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	})
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
	req.Header.Set("Upgrade", "websocket")
	req.Header.Set("Connection", "Upgrade")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != 200 {
		t.Fatalf("status %d %s", rec.Code, rec.Body.String())
	}
	if sawUpgrade != "" {
		t.Fatalf("upgrade forwarded on sse endpoint: %q", sawUpgrade)
	}
}

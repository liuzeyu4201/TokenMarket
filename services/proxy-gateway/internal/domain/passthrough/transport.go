package passthrough

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"
)

var (
	errSlowConsumer  = errors.New(CodeSlowConsumer)
	errUploadTimeout = errors.New("upload timeout")
)

type timedRT struct {
	next http.RoundTripper
	d    *time.Duration
}

func (t timedRT) RoundTrip(r *http.Request) (*http.Response, error) {
	next := t.next
	if next == nil {
		next = http.DefaultTransport
	}
	start := time.Now()
	resp, err := next.RoundTrip(r)
	if t.d != nil {
		*t.d = time.Since(start)
	}
	return resp, err
}

func websocketUpgrade(r *http.Request) bool {
	if r == nil {
		return false
	}
	return strings.EqualFold(r.Header.Get("Upgrade"), "websocket")
}

type streamWriter struct {
	http.ResponseWriter
	status int
	idle   time.Duration
	flush  bool
}

func (w *streamWriter) WriteHeader(code int) {
	if w.status == 0 {
		w.status = code
	}
	w.ResponseWriter.WriteHeader(code)
}

func (w *streamWriter) Write(p []byte) (int, error) {
	if w.status == 0 {
		w.status = http.StatusOK
	}
	if w.idle > 0 {
		if err := http.NewResponseController(w.ResponseWriter).SetWriteDeadline(time.Now().Add(w.idle)); err != nil {
			n, err2 := writeWithIdle(w.ResponseWriter, p, w.idle)
			w.maybeFlush()
			return n, err2
		}
	}
	n, err := w.ResponseWriter.Write(p)
	w.maybeFlush()
	return n, err
}

func (w *streamWriter) maybeFlush() {
	if !w.flush {
		return
	}
	if f, ok := w.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

func (w *streamWriter) Flush() {
	if f, ok := w.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}

func (w *streamWriter) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	h, ok := w.ResponseWriter.(http.Hijacker)
	if !ok {
		return nil, nil, errors.New("hijack not supported")
	}
	return h.Hijack()
}

func (w *streamWriter) Unwrap() http.ResponseWriter { return w.ResponseWriter }

func writeWithIdle(w io.Writer, p []byte, idle time.Duration) (int, error) {
	type res struct {
		n   int
		err error
	}
	ch := make(chan res, 1)
	go func() {
		n, err := w.Write(p)
		ch <- res{n, err}
	}()
	timer := time.NewTimer(idle)
	defer timer.Stop()
	select {
	case r := <-ch:
		return r.n, r.err
	case <-timer.C:
		return 0, errSlowConsumer
	}
}

const idTeeLimit = 64 << 10

type idTee struct {
	src  io.ReadCloser
	buf  bytes.Buffer
	max  int
	once sync.Once
	onID func(string)
}

func newIDTee(src io.ReadCloser, onID func(string)) *idTee {
	return &idTee{src: src, max: idTeeLimit, onID: onID}
}

func (t *idTee) Read(p []byte) (int, error) {
	n, err := t.src.Read(p)
	if n > 0 && t.buf.Len() < t.max {
		take := n
		if t.buf.Len()+take > t.max {
			take = t.max - t.buf.Len()
		}
		_, _ = t.buf.Write(p[:take])
	}
	if err == io.EOF || t.buf.Len() >= t.max {
		t.finish()
	}
	return n, err
}

func (t *idTee) Close() error {
	t.finish()
	if t.src == nil {
		return nil
	}
	return t.src.Close()
}

func (t *idTee) finish() {
	t.once.Do(func() {
		if t.onID == nil {
			return
		}
		if id := topLevelID(t.buf.Bytes()); id != "" {
			t.onID(id)
		}
	})
}

func topLevelID(b []byte) string {
	dec := json.NewDecoder(bytes.NewReader(b))
	tok, err := dec.Token()
	if err != nil {
		return ""
	}
	d, ok := tok.(json.Delim)
	if !ok || d != '{' {
		return ""
	}
	var fallback string
	for dec.More() {
		kt, err := dec.Token()
		if err != nil {
			break
		}
		ks, _ := kt.(string)
		var val any
		if err := dec.Decode(&val); err != nil {
			break
		}
		s, ok := val.(string)
		if !ok || s == "" {
			continue
		}
		if ks == "id" {
			return s
		}
		if fallback == "" && strings.HasSuffix(ks, "_id") {
			fallback = s
		}
		if fallback == "" && ks == "name" {
			fallback = lastPathSegment(s)
		}
	}
	return fallback
}

func lastPathSegment(s string) string {
	s = strings.Trim(s, "/")
	if s == "" {
		return ""
	}
	if i := strings.LastIndexByte(s, '/'); i >= 0 && i+1 < len(s) {
		return s[i+1:]
	}
	return s
}

type deadlineReadCloser struct {
	io.ReadCloser
	deadline time.Time
}

func (d *deadlineReadCloser) Read(p []byte) (int, error) {
	if !d.deadline.IsZero() && time.Now().After(d.deadline) {
		return 0, errUploadTimeout
	}
	return d.ReadCloser.Read(p)
}

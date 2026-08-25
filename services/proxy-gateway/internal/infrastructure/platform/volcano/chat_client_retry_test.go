package volcano_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync/atomic"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

func TestChatClientNoRetryOn5xx(t *testing.T) {
	var n atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n.Add(1)
		w.WriteHeader(502)
		_, _ = w.Write([]byte(`{"error":"tmp"}`))
	}))
	defer srv.Close()
	c := volcano.NewChatClient(srv.URL)
	if c.MaxAttempts != 1 {
		t.Fatalf("MaxAttempts=%d", c.MaxAttempts)
	}
	res := c.PostJSON(context.Background(), "sk-synthetic-test-key-not-real", []byte(`{}`), false)
	if res.Status != 502 {
		t.Fatal(res.Status)
	}
	if n.Load() != 1 {
		t.Fatalf("calls %d", n.Load())
	}
}

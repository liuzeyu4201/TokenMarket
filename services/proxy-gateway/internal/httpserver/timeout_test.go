package httpserver_test

import (
	"bufio"
	"io"
	"net"
	"net/http"
	"strings"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keypool"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/httpserver"
)

func TestPartialHeadersClosedWithinDeadline(t *testing.T) {
	h := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("handler must not run for incomplete headers")
	})
	srv := httpserver.NewPublicHTTPServerTimeouts("127.0.0.1:0", h, 80*time.Millisecond, time.Second)
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	go func() { _ = srv.Serve(ln) }()
	t.Cleanup(func() { _ = srv.Close() })

	conn, err := net.Dial("tcp", ln.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	if _, err := conn.Write([]byte("POST /health/live HTTP/1.1\r\nHost: 127.0.0.1\r\n")); err != nil {
		t.Fatal(err)
	}
	_ = conn.SetReadDeadline(time.Now().Add(time.Second))
	buf := make([]byte, 8)
	_, err = conn.Read(buf)
	if err == nil {
		t.Fatal("expected the server to close the stalled header connection")
	}
}

func TestSSEWriteIdleReleasesSellerLease(t *testing.T) {
	payload := strings.Repeat("data: {\"id\":\"c1\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"a\"}}]}\n\n", 2000)
	st := &stubPoster{status: 200, stream: io.NopCloser(strings.NewReader(payload))}
	pool := keypool.New([]keypool.SellerKey{{
		ID: "sk1", SellerID: "seller-9", APIKey: "sk-synthetic-upstream", Admin: "active", Health: "healthy",
	}}, 1)
	h := proxyHandler(t, st, pool, "buyer-1", nil)
	srv := httpserver.NewPublicHTTPServerTimeouts("127.0.0.1:0", h, time.Second, time.Second)
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer ln.Close()
	go func() { _ = srv.Serve(ln) }()
	t.Cleanup(func() { _ = srv.Close() })

	conn, err := net.Dial("tcp", ln.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	body := `{"model":"doubao-pro-32k","stream":true,"messages":[{"role":"user","content":"hi"}]}`
	req := "POST /v1/proxy/volcano/chat/completions HTTP/1.1\r\n" +
		"Host: 127.0.0.1\r\n" +
		"Authorization: Bearer " + testProxySecret + "\r\n" +
		"Content-Type: application/json\r\n" +
		"Content-Length: " + itoa(len(body)) + "\r\n\r\n" + body
	if _, err := conn.Write([]byte(req)); err != nil {
		t.Fatal(err)
	}
	_ = conn.SetReadDeadline(time.Now().Add(150 * time.Millisecond))
	r := bufio.NewReader(conn)
	_, _ = r.ReadString('\n')
	_ = conn.Close() // stop reading so subsequent writes idle out

	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		_, ok := pool.Pick("buyer-1")
		if ok {
			return
		}
		time.Sleep(20 * time.Millisecond)
	}
	t.Fatal("seller lease was not released after write-idle")
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var b [16]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	return string(b[i:])
}

func TestPublicHTTPServerSetsHeaderTimeout(t *testing.T) {
	srv := httpserver.NewPublicHTTPServer("127.0.0.1:0", http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	if srv.ReadHeaderTimeout != httpserver.DefaultReadHeaderTimeout {
		t.Fatalf("header timeout %s", srv.ReadHeaderTimeout)
	}
	if srv.IdleTimeout != httpserver.DefaultIdleTimeout {
		t.Fatalf("idle %s", srv.IdleTimeout)
	}
	if srv.MaxHeaderBytes != httpserver.DefaultMaxHeaderBytes {
		t.Fatalf("max header %d", srv.MaxHeaderBytes)
	}
}

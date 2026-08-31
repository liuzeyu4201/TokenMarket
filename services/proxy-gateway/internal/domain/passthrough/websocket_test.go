package passthrough

import (
	"bufio"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

func wsCatalog() *endpcatalog.Catalog {
	return &endpcatalog.Catalog{
		CatalogMajor: 1,
		Providers:    []string{"openai", "anthropic", "vertex"},
		Records: []endpcatalog.EndpointRecord{
			{
				ID:           "openai.websocket.v1.realtime",
				Provider:     "openai",
				Method:       "WEBSOCKET",
				PathTemplate: "/v1/realtime",
				Stability:    "stable",
				Stateful:     true,
				Transport:    "websocket",
				Affinity:     "connection",
			},
		},
	}
}

func TestWebsocketUpgradeForwardedAndEcho(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.EqualFold(r.Header.Get("Upgrade"), "websocket") {
			http.Error(w, "missing upgrade", http.StatusBadRequest)
			return
		}
		if !strings.Contains(strings.ToLower(r.Header.Get("Connection")), "upgrade") {
			http.Error(w, "missing connection", http.StatusBadRequest)
			return
		}
		hj, ok := w.(http.Hijacker)
		if !ok {
			http.Error(w, "no hijack", 500)
			return
		}
		conn, bufrw, err := hj.Hijack()
		if err != nil {
			return
		}
		defer conn.Close()
		_, _ = bufrw.WriteString("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n")
		_ = bufrw.Flush()
		buf := make([]byte, 32)
		n, _ := bufrw.Read(buf)
		_, _ = bufrw.Write(buf[:n])
		_ = bufrw.Flush()
	}))
	t.Cleanup(up.Close)
	k := &Kernel{
		Catalog:  wsCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "sk-up", ConnectionID: "conn-ws"}},
	}
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		k.ServeHTTP(w, r, "dedicated", false)
	}))
	t.Cleanup(proxy.Close)

	conn, err := net.Dial("tcp", proxy.Listener.Addr().String())
	if err != nil {
		t.Fatal(err)
	}
	defer conn.Close()
	_ = conn.SetDeadline(time.Now().Add(2 * time.Second))
	// RFC 6455 sample nonce ("the sample nonce"); inert handshake fixture, not a credential.
	req := fmt.Sprintf("GET /openai/v1/realtime HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n", proxy.Listener.Addr().String())
	if _, err := io.WriteString(conn, req); err != nil {
		t.Fatal(err)
	}
	br := bufio.NewReader(conn)
	status, err := br.ReadString('\n')
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(status, "101") {
		t.Fatalf("status line %q", status)
	}
	for {
		line, err := br.ReadString('\n')
		if err != nil {
			t.Fatal(err)
		}
		if line == "\r\n" {
			break
		}
	}
	if _, err := io.WriteString(conn, "ping-frame"); err != nil {
		t.Fatal(err)
	}
	buf := make([]byte, 16)
	n, err := br.Read(buf)
	if err != nil {
		t.Fatal(err)
	}
	if string(buf[:n]) != "ping-frame" {
		t.Fatalf("echo %q", buf[:n])
	}
}

func TestWebsocketSharedRejected(t *testing.T) {
	var n int
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n++
		w.WriteHeader(200)
	}))
	t.Cleanup(up.Close)
	k := &Kernel{
		Catalog:  wsCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}},
	}
	req := httptest.NewRequest(http.MethodGet, "/openai/v1/realtime", nil)
	req.Header.Set("Upgrade", "websocket")
	req.Header.Set("Connection", "Upgrade")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	if rec.Code != http.StatusForbidden {
		t.Fatalf("status %d body %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Body.String(), endpcatalog.CodeDedicatedRequired) {
		t.Fatalf("body %s", rec.Body.String())
	}
	if n != 0 {
		t.Fatal("shared stateful websocket forwarded")
	}
}

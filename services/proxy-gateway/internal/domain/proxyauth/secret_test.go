package proxyauth_test

import (
	"bytes"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
)

func TestLoadSharedSecretFailClosed(t *testing.T) {
	if _, err := proxyauth.LoadSharedSecret(""); err == nil {
		t.Fatal("missing")
	}
	if _, err := proxyauth.LoadSharedSecret("abc"); err == nil {
		t.Fatal("malformed/undersized hex")
	}
	if _, err := proxyauth.LoadSharedSecret(strings.Repeat("aa", 16)); err == nil {
		t.Fatal("undersized hex")
	}
	if _, err := proxyauth.LoadSharedSecret("short"); err == nil {
		t.Fatal("undersized utf8")
	}
	got, err := proxyauth.LoadSharedSecret(strings.Repeat("ab", 32))
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 32 {
		t.Fatalf("len %d", len(got))
	}
	raw := strings.Repeat("x", 32)
	got2, err := proxyauth.LoadSharedSecret(raw)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(got2, []byte(raw)) {
		t.Fatal("utf8 secret")
	}
}

func TestSamePepperHashesStayCompatible(t *testing.T) {
	pepper, err := proxyauth.LoadSharedSecret(strings.Repeat("cd", 32))
	if err != nil {
		t.Fatal(err)
	}
	sec := "tmk-0123456789abcdef0123456789abcdef"
	h1 := proxyauth.HashSecret(pepper, sec)
	h2 := proxyauth.HashSecret(pepper, sec)
	if h1 != h2 {
		t.Fatal("restart with same secret must keep hashes")
	}
}

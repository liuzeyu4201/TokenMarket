package proxyauth_test

import (
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
)

type mem struct{ m map[string]proxyauth.Record }

func (m mem) Lookup(h string) (proxyauth.Record, bool) {
	r, ok := m.m[h]
	return r, ok
}

func TestBearerAuth(t *testing.T) {
	pepper := []byte("p")
	sec := "tmk-0123456789abcdef0123456789abcdef"
	h := proxyauth.HashSecret(pepper, sec)
	st := mem{m: map[string]proxyauth.Record{
		h: {KeyID: "1", BuyerID: "b", Platform: "volcano", Status: "active"},
	}}
	a := proxyauth.Authenticator{Pepper: pepper, Store: st}
	rec, ok := a.Authenticate("Bearer " + sec)
	if !ok || rec.BuyerID != "b" {
		t.Fatal(rec, ok)
	}
	if _, ok := a.Authenticate("Bearer nope"); ok {
		t.Fatal("bad secret")
	}
	if proxyauth.ParseBearer("Token x") != "" {
		t.Fatal("scheme")
	}
	if _, ok := a.Authenticate("Bearer tm_pk_" + strings.Repeat("ab", 16)); ok {
		t.Fatal("wrong prefix")
	}
}

func TestMapStoreAndNilAuthenticator(t *testing.T) {
	var empty proxyauth.MapStore
	if _, ok := empty.Lookup("x"); ok {
		t.Fatal("empty")
	}
	st := proxyauth.MapStore{Records: map[string]proxyauth.Record{"h": {KeyID: "1", Status: "active"}}}
	if rec, ok := st.Lookup("h"); !ok || rec.KeyID != "1" {
		t.Fatal(rec, ok)
	}
	a := proxyauth.Authenticator{Pepper: []byte("p"), Store: nil}
	if _, ok := a.Authenticate("Bearer tmk-0123456789abcdef0123456789abcdef"); ok {
		t.Fatal("nil store")
	}
}

func TestValidProxySecret(t *testing.T) {
	if proxyauth.ValidProxySecret("tm_pk_" + strings.Repeat("a", 32)) {
		t.Fatal("old prefix")
	}
	if proxyauth.ValidProxySecret("tmk-short") {
		t.Fatal("entropy")
	}
	if !proxyauth.ValidProxySecret("tmk-0123456789abcdef0123456789abcdef") {
		t.Fatal("want valid")
	}
}

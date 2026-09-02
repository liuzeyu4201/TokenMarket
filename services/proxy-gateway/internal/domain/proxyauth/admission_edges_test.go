package proxyauth_test

import (
	"encoding/hex"
	"strings"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
)

type resultStore struct {
	rec proxyauth.Record
	st  proxyauth.LookupStatus
}

func (s resultStore) Lookup(hashHex string) (proxyauth.Record, bool) {
	rec, st := s.LookupResult(hashHex)
	return rec, st == proxyauth.LookupHit
}

func (s resultStore) LookupResult(hashHex string) (proxyauth.Record, proxyauth.LookupStatus) {
	return s.rec, s.st
}

func TestAuthStatusOK(t *testing.T) {
	if !proxyauth.AuthOK.OK() {
		t.Fatal("AuthOK")
	}
	if proxyauth.AuthInvalid.OK() || proxyauth.AuthOverload.OK() {
		t.Fatal("non-ok")
	}
}

func TestAdmissionLimiterDefaultsAndNil(t *testing.T) {
	var none *proxyauth.AdmissionLimiter
	if !none.AllowLookup() || !none.AllowValidLookup() {
		t.Fatal("nil limiter must not block")
	}
	none.FinishLookup()
	none.SetClock(time.Now)
	if none.CachedHit("x") || none.CachedMiss("x") {
		t.Fatal("nil cache")
	}
	if none.NegativeSize() != 0 || none.NegativeCap() != 0 {
		t.Fatal("nil sizes")
	}
	lim := proxyauth.NewAdmissionLimiter(0, 0, 0)
	if lim.NegativeCap() != 4096 {
		t.Fatalf("cap %d", lim.NegativeCap())
	}
	if !lim.AllowValidLookup() {
		t.Fatal("first valid lookup")
	}
	if lim.AllowValidLookup() {
		t.Fatal("in-flight cap")
	}
	lim.FinishLookup()
	lim.FinishLookup()
}

func TestAdmissionCacheHitMissExpiryAndEvict(t *testing.T) {
	lim := proxyauth.NewAdmissionLimiter(8, 8, 8)
	now := time.Unix(1_700_000_000, 0)
	lim.SetClock(func() time.Time { return now })
	hash := strings.Repeat("ab", 16)
	lim.RememberHit(hash)
	if !lim.CachedHit(hash) {
		t.Fatal("hit")
	}
	now = now.Add(2 * time.Second)
	if lim.CachedHit(hash) {
		t.Fatal("expired hit")
	}
	lim.RememberMiss(hash)
	if !lim.CachedMiss(hash) {
		t.Fatal("miss")
	}
	now = now.Add(3 * time.Second)
	if lim.CachedMiss(hash) {
		t.Fatal("expired miss")
	}
	if lim.CachedHit("") || lim.CachedMiss("") {
		t.Fatal("empty hash")
	}
	for i := 0; i < 5000; i++ {
		lim.RememberMiss(hex.EncodeToString([]byte{byte(i >> 8), byte(i)}))
	}
	if lim.NegativeSize() > lim.NegativeCap() {
		t.Fatalf("evict failed %d > %d", lim.NegativeSize(), lim.NegativeCap())
	}
	// Clock going backwards should not panic refill.
	now = now.Add(-time.Hour)
	_ = lim.AllowLookup()
}

func TestAuthenticateStatusResultStoreAndCachedPaths(t *testing.T) {
	pepper := []byte("pep")
	sec := "tmk-" + strings.Repeat("ab", 16)
	hash := proxyauth.HashSecret(pepper, sec)
	active := proxyauth.Record{KeyID: "1", BuyerID: "b", Status: "active"}
	lim := proxyauth.NewAdmissionLimiter(8, 8, 8)
	a := proxyauth.Authenticator{
		Pepper:  pepper,
		Store:   resultStore{rec: active, st: proxyauth.LookupHit},
		Limiter: lim,
	}
	rec, st := a.AuthenticateStatus("Bearer " + sec)
	if st != proxyauth.AuthOK || rec.BuyerID != "b" {
		t.Fatalf("hit %+v %v", rec, st)
	}
	if !lim.CachedHit(hash) {
		t.Fatal("remember hit")
	}
	_, st = a.AuthenticateStatus("Bearer " + sec)
	if st != proxyauth.AuthOK {
		t.Fatalf("cached hit %v", st)
	}
	a.Store = resultStore{st: proxyauth.LookupUnavailable}
	_, st = a.AuthenticateStatus("Bearer " + sec)
	if st != proxyauth.AuthInvalid {
		t.Fatalf("unavailable %v", st)
	}
	a.Store = resultStore{st: proxyauth.LookupMiss}
	lim2 := proxyauth.NewAdmissionLimiter(8, 8, 8)
	a.Limiter = lim2
	_, st = a.AuthenticateStatus("Bearer " + sec)
	if st != proxyauth.AuthInvalid {
		t.Fatalf("miss %v", st)
	}
	if !lim2.CachedMiss(hash) {
		t.Fatal("remember miss")
	}
	_, st = a.AuthenticateStatus("Bearer " + sec)
	if st != proxyauth.AuthInvalid {
		t.Fatalf("cached miss %v", st)
	}
	inactive := proxyauth.Record{KeyID: "1", Status: "disabled"}
	a.Store = resultStore{rec: inactive, st: proxyauth.LookupHit}
	a.Limiter = proxyauth.NewAdmissionLimiter(8, 8, 8)
	_, st = a.AuthenticateStatus("Bearer " + sec)
	if st != proxyauth.AuthInvalid {
		t.Fatalf("inactive %v", st)
	}
	if !proxyauth.ValidProxySecret(sec) {
		t.Fatal("valid secret")
	}
	if proxyauth.ValidProxySecret("tmk-zz") || proxyauth.ValidProxySecret("pk-"+strings.Repeat("ab", 16)) {
		t.Fatal("invalid secrets")
	}
	if proxyauth.ValidProxySecret("tmk-" + strings.Repeat("gg", 16)) {
		t.Fatal("non-hex")
	}
}

func TestLoadSharedSecretEdges(t *testing.T) {
	if _, err := proxyauth.LoadSharedSecret(""); err == nil {
		t.Fatal("missing")
	}
	if _, err := proxyauth.LoadSharedSecret("abc"); err == nil {
		t.Fatal("undersized text")
	}
	if _, err := proxyauth.LoadSharedSecret("abcd"); err == nil {
		t.Fatal("short hex")
	}
	odd := strings.Repeat("a", 33)
	if _, err := proxyauth.LoadSharedSecret(odd); err == nil {
		t.Fatal("odd hex")
	}
	ok, err := proxyauth.LoadSharedSecret(strings.Repeat("ab", 32))
	if err != nil || len(ok) != 32 {
		t.Fatal(err, len(ok))
	}
}

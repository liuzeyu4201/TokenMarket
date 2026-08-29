package proxyauth_test

import (
	"fmt"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
)

type countingStore struct {
	n atomic.Int64
}

func (c *countingStore) Lookup(hashHex string) (proxyauth.Record, bool) {
	c.n.Add(1)
	return proxyauth.Record{}, false
}

type statusStore struct {
	status proxyauth.LookupStatus
	n      atomic.Int64
}

func (s *statusStore) Lookup(hashHex string) (proxyauth.Record, bool) {
	rec, st := s.LookupResult(hashHex)
	return rec, st == proxyauth.LookupHit
}

func (s *statusStore) LookupResult(hashHex string) (proxyauth.Record, proxyauth.LookupStatus) {
	s.n.Add(1)
	return proxyauth.Record{}, s.status
}

func TestFloodUniqueKeysMostlyRejectedBeforeLookup(t *testing.T) {
	store := &countingStore{}
	lim := proxyauth.NewAdmissionLimiter(4, 0.01, 4)
	a := proxyauth.Authenticator{Pepper: []byte("pep"), Store: store, Limiter: lim}
	for i := 0; i < 40; i++ {
		sec := fmt.Sprintf("tmk-%032x", i+1)
		_, _ = a.Authenticate("Bearer " + sec)
	}
	lookups := store.n.Load()
	if lookups > 10 {
		t.Fatalf("lookups %d; flood should be admission-limited", lookups)
	}
	if lookups == 0 {
		t.Fatal("expected some lookups")
	}
}

func TestUniqueInvalidKeysDoNotExhaustValidBuyer(t *testing.T) {
	pepper := []byte("pep")
	sec := "tmk-" + strings.Repeat("ab", 16)
	h := proxyauth.HashSecret(pepper, sec)
	st := proxyauth.MapStore{Records: map[string]proxyauth.Record{
		h: {KeyID: "1", BuyerID: "buyer", Platform: "volcano", Status: "active"},
	}}
	lim := proxyauth.NewAdmissionLimiter(4, 0.01, 4)
	a := proxyauth.Authenticator{Pepper: pepper, Store: st, Limiter: lim}
	rec, status := a.AuthenticateStatus("Bearer " + sec)
	if status != proxyauth.AuthOK || rec.BuyerID != "buyer" {
		t.Fatalf("prime valid: %+v %v", rec, status)
	}
	overload := 0
	invalid := 0
	for i := 0; i < 40; i++ {
		uniq := fmt.Sprintf("tmk-%032x", i+1)
		_, st := a.AuthenticateStatus("Bearer " + uniq)
		switch st {
		case proxyauth.AuthOverload:
			overload++
		case proxyauth.AuthInvalid:
			invalid++
		case proxyauth.AuthOK:
			t.Fatal("unique miss must not authenticate")
		}
	}
	if overload == 0 {
		t.Fatal("expected overload after miss budget exhaustion")
	}
	_, again := a.AuthenticateStatus("Bearer " + sec)
	if again != proxyauth.AuthOK {
		t.Fatalf("valid buyer lost capacity; status=%v overload=%d invalid=%d", again, overload, invalid)
	}
}

func TestOverloadIsNotInvalidCredential(t *testing.T) {
	lim := proxyauth.NewAdmissionLimiter(1, 0.0001, 1)
	a := proxyauth.Authenticator{Pepper: []byte("pep"), Store: &countingStore{}, Limiter: lim}
	_, first := a.AuthenticateStatus("Bearer tmk-" + strings.Repeat("11", 16))
	if first == proxyauth.AuthOK {
		t.Fatal("miss")
	}
	_, second := a.AuthenticateStatus("Bearer tmk-" + strings.Repeat("22", 16))
	if second != proxyauth.AuthOverload {
		t.Fatalf("want overload got %v", second)
	}
	if second == proxyauth.AuthInvalid {
		t.Fatal("overload must not be reported as invalid credentials")
	}
}

func TestNegativeCacheBoundedAndExpiresWithoutRequery(t *testing.T) {
	lim := proxyauth.NewAdmissionLimiter(1024, 1024, 1024)
	now := time.Now()
	lim.SetClock(func() time.Time { return now })
	for i := 0; i < lim.NegativeCap()+50; i++ {
		lim.RememberMiss(fmt.Sprintf("%064x", i+1))
	}
	if lim.NegativeSize() > lim.NegativeCap() {
		t.Fatalf("size %d cap %d", lim.NegativeSize(), lim.NegativeCap())
	}
	now = now.Add(5 * time.Second)
	if lim.NegativeSize() != 0 {
		t.Fatalf("expired entries remain %d", lim.NegativeSize())
	}
}

func TestTransientFailureNotCachedAsMiss(t *testing.T) {
	st := &statusStore{status: proxyauth.LookupUnavailable}
	lim := proxyauth.NewAdmissionLimiter(32, 32, 32)
	a := proxyauth.Authenticator{Pepper: []byte("pep"), Store: st, Limiter: lim}
	sec := "tmk-" + strings.Repeat("ab", 16)
	_, ok := a.Authenticate("Bearer " + sec)
	if ok {
		t.Fatal("transient must not authenticate")
	}
	if st.n.Load() != 1 {
		t.Fatalf("lookups %d", st.n.Load())
	}
	st.status = proxyauth.LookupMiss
	_, ok = a.Authenticate("Bearer " + sec)
	if ok {
		t.Fatal("miss")
	}
	if st.n.Load() != 2 {
		t.Fatalf("transient must not be cached as miss; lookups %d", st.n.Load())
	}
}

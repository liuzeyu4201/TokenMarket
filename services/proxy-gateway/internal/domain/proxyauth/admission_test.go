package proxyauth_test

import (
	"fmt"
	"strings"
	"sync/atomic"
	"testing"

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

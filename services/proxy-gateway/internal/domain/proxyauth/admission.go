package proxyauth

import (
	"sync"
	"time"
)

// LookupStatus distinguishes authoritative misses from transient lookup failures.
type LookupStatus int

const (
	LookupHit LookupStatus = iota
	LookupMiss
	LookupUnavailable
)

// ResultStore optionally reports lookup status so misses can be cached safely.
type ResultStore interface {
	LookupResult(hashHex string) (Record, LookupStatus)
}

// AdmissionLimiter bounds failed-auth lookups before the fact store is touched.
type AdmissionLimiter struct {
	mu          sync.Mutex
	tokens      float64
	burst       float64
	ratePerSec  float64
	last        time.Time
	neg         map[string]time.Time
	negTTL      time.Duration
	inFlight    int
	maxInFlight int
}

func NewAdmissionLimiter(burst int, ratePerSec float64, maxInFlight int) *AdmissionLimiter {
	if burst < 1 {
		burst = 1
	}
	if ratePerSec <= 0 {
		ratePerSec = 1
	}
	if maxInFlight < 1 {
		maxInFlight = burst
	}
	return &AdmissionLimiter{
		tokens:      float64(burst),
		burst:       float64(burst),
		ratePerSec:  ratePerSec,
		last:        time.Now(),
		neg:         map[string]time.Time{},
		negTTL:      2 * time.Second,
		maxInFlight: maxInFlight,
	}
}

// AllowLookup consumes a token. False means reject before the fact-store call.
func (a *AdmissionLimiter) AllowLookup() bool {
	if a == nil {
		return true
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	now := time.Now()
	elapsed := now.Sub(a.last).Seconds()
	a.tokens += elapsed * a.ratePerSec
	if a.tokens > a.burst {
		a.tokens = a.burst
	}
	a.last = now
	if a.inFlight >= a.maxInFlight || a.tokens < 1 {
		return false
	}
	a.tokens--
	a.inFlight++
	return true
}

func (a *AdmissionLimiter) FinishLookup() {
	if a == nil {
		return
	}
	a.mu.Lock()
	if a.inFlight > 0 {
		a.inFlight--
	}
	a.mu.Unlock()
}

func (a *AdmissionLimiter) CachedMiss(hashHex string) bool {
	if a == nil || hashHex == "" {
		return false
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	exp, ok := a.neg[hashHex]
	if !ok {
		return false
	}
	if time.Now().After(exp) {
		delete(a.neg, hashHex)
		return false
	}
	return true
}

func (a *AdmissionLimiter) RememberMiss(hashHex string) {
	if a == nil || hashHex == "" {
		return
	}
	a.mu.Lock()
	a.neg[hashHex] = time.Now().Add(a.negTTL)
	a.mu.Unlock()
}

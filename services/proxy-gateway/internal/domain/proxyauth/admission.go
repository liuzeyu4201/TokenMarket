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

// AuthStatus is the public authentication outcome. Overload is distinct from Invalid.
type AuthStatus int

const (
	AuthOK AuthStatus = iota
	AuthInvalid
	AuthOverload
)

func (s AuthStatus) OK() bool { return s == AuthOK }

// ResultStore optionally reports lookup status so misses can be cached safely.
type ResultStore interface {
	LookupResult(hashHex string) (Record, LookupStatus)
}

const (
	defaultNegCap = 4096
	defaultPosCap = 4096
	defaultNegTTL = 2 * time.Second
	defaultPosTTL = 1 * time.Second
)

// AdmissionLimiter bounds failed-auth lookups separately from valid traffic.
type AdmissionLimiter struct {
	mu          sync.Mutex
	tokens      float64
	burst       float64
	ratePerSec  float64
	last        time.Time
	neg         map[string]time.Time
	negOrder    []string
	negTTL      time.Duration
	negCap      int
	pos         map[string]time.Time
	posOrder    []string
	posTTL      time.Duration
	posCap      int
	inFlight    int
	maxInFlight int
	nowFn       func() time.Time
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
		negTTL:      defaultNegTTL,
		negCap:      defaultNegCap,
		pos:         map[string]time.Time{},
		posTTL:      defaultPosTTL,
		posCap:      defaultPosCap,
		maxInFlight: maxInFlight,
	}
}

func (a *AdmissionLimiter) now() time.Time {
	if a != nil && a.nowFn != nil {
		return a.nowFn()
	}
	return time.Now()
}

// SetClock injects a clock for tests.
func (a *AdmissionLimiter) SetClock(now func() time.Time) {
	if a == nil {
		return
	}
	a.mu.Lock()
	a.nowFn = now
	a.mu.Unlock()
}

func (a *AdmissionLimiter) refillLocked(now time.Time) {
	elapsed := now.Sub(a.last).Seconds()
	if elapsed < 0 {
		elapsed = 0
	}
	a.tokens += elapsed * a.ratePerSec
	if a.tokens > a.burst {
		a.tokens = a.burst
	}
	a.last = now
}

func (a *AdmissionLimiter) sweepLocked(now time.Time) {
	for k, exp := range a.neg {
		if now.After(exp) {
			delete(a.neg, k)
		}
	}
	filtered := a.negOrder[:0]
	for _, k := range a.negOrder {
		if _, ok := a.neg[k]; ok {
			filtered = append(filtered, k)
		}
	}
	a.negOrder = filtered
	for k, exp := range a.pos {
		if now.After(exp) {
			delete(a.pos, k)
		}
	}
	pfiltered := a.posOrder[:0]
	for _, k := range a.posOrder {
		if _, ok := a.pos[k]; ok {
			pfiltered = append(pfiltered, k)
		}
	}
	a.posOrder = pfiltered
}

func (a *AdmissionLimiter) evictLocked(m map[string]time.Time, order *[]string, cap int) {
	for len(m) > cap && len(*order) > 0 {
		oldest := (*order)[0]
		*order = (*order)[1:]
		delete(m, oldest)
	}
}

// CachedHit reports a still-valid positive cache entry.
func (a *AdmissionLimiter) CachedHit(hashHex string) bool {
	if a == nil || hashHex == "" {
		return false
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	now := a.now()
	a.sweepLocked(now)
	exp, ok := a.pos[hashHex]
	if !ok || now.After(exp) {
		if ok {
			delete(a.pos, hashHex)
		}
		return false
	}
	return true
}

// AllowLookup consumes a miss token and an in-flight slot for an uncached secret.
// Valid (positive-cached) traffic must not call this.
func (a *AdmissionLimiter) AllowLookup() bool {
	if a == nil {
		return true
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	now := a.now()
	a.refillLocked(now)
	a.sweepLocked(now)
	if a.inFlight >= a.maxInFlight || a.tokens < 1 {
		return false
	}
	a.tokens--
	a.inFlight++
	return true
}

// AllowValidLookup reserves concurrency for a known-valid or first-time valid path
// without consuming the miss abuse bucket.
func (a *AdmissionLimiter) AllowValidLookup() bool {
	if a == nil {
		return true
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	now := a.now()
	a.sweepLocked(now)
	if a.inFlight >= a.maxInFlight {
		return false
	}
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
	now := a.now()
	a.sweepLocked(now)
	exp, ok := a.neg[hashHex]
	if !ok {
		return false
	}
	if now.After(exp) {
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
	now := a.now()
	a.sweepLocked(now)
	if _, exists := a.neg[hashHex]; !exists {
		a.negOrder = append(a.negOrder, hashHex)
	}
	a.neg[hashHex] = now.Add(a.negTTL)
	a.evictLocked(a.neg, &a.negOrder, a.negCap)
	delete(a.pos, hashHex)
	a.mu.Unlock()
}

func (a *AdmissionLimiter) RememberHit(hashHex string) {
	if a == nil || hashHex == "" {
		return
	}
	a.mu.Lock()
	now := a.now()
	a.sweepLocked(now)
	if _, exists := a.pos[hashHex]; !exists {
		a.posOrder = append(a.posOrder, hashHex)
	}
	a.pos[hashHex] = now.Add(a.posTTL)
	a.evictLocked(a.pos, &a.posOrder, a.posCap)
	delete(a.neg, hashHex)
	a.mu.Unlock()
}

func (a *AdmissionLimiter) NegativeSize() int {
	if a == nil {
		return 0
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	a.sweepLocked(a.now())
	return len(a.neg)
}

func (a *AdmissionLimiter) NegativeCap() int {
	if a == nil {
		return 0
	}
	return a.negCap
}

// Package pricelock snapshots published rate/buyer/seller versions at request accept.
package pricelock

import "sync"

// Snapshot is an immutable price lock for one request.
type Snapshot struct {
	RateVersion string
	BuyerBPS    int
	SellerBPS   int
}

// Locker copies the current published snapshot onto a request_id.
type Locker struct {
	mu      sync.Mutex
	current Snapshot
	ready   bool
	byReq   map[string]Snapshot
}

func NewLocker() *Locker {
	return &Locker{byReq: map[string]Snapshot{}}
}

func (l *Locker) Publish(s Snapshot) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.current = s
	l.ready = true
}

func (l *Locker) Lock(requestID string) (Snapshot, bool) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if existing, ok := l.byReq[requestID]; ok {
		return existing, true
	}
	if !l.ready || requestID == "" {
		return Snapshot{}, false
	}
	s := l.current
	l.byReq[requestID] = s
	return s, true
}

func (l *Locker) Get(requestID string) (Snapshot, bool) {
	l.mu.Lock()
	defer l.mu.Unlock()
	s, ok := l.byReq[requestID]
	return s, ok
}

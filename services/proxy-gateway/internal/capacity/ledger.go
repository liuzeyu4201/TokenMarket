package capacity

import (
	"context"
	"sync"
	"time"
)

type reservation struct {
	RequestID string
	ProjectID string
	KeyID     string
	Amount    int64
	State     string
}

type MemLedger struct {
	mu           sync.Mutex
	open         map[string]reservation
	settled      map[string]reservation
	aborted      map[string]reservation
	DoubleCharge int
	Leaks        int
}

func NewMemLedger() *MemLedger {
	return &MemLedger{
		open:    map[string]reservation{},
		settled: map[string]reservation{},
		aborted: map[string]reservation{},
	}
}

func (l *MemLedger) Reserve(_ context.Context, requestID, projectID, keyID string, amount int64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if cur, ok := l.open[requestID]; ok {
		if cur.ProjectID != projectID || cur.KeyID != keyID {
			l.Leaks++
			return nil
		}
		return nil
	}
	if cur, ok := l.settled[requestID]; ok {
		if cur.ProjectID != projectID {
			l.Leaks++
		}
		l.DoubleCharge++
		return nil
	}
	l.open[requestID] = reservation{
		RequestID: requestID,
		ProjectID: projectID,
		KeyID:     keyID,
		Amount:    amount,
		State:     "open",
	}
	return nil
}

func (l *MemLedger) Abort(_ context.Context, requestID string) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if cur, ok := l.open[requestID]; ok {
		delete(l.open, requestID)
		cur.State = "aborted"
		l.aborted[requestID] = cur
	}
	return nil
}

func (l *MemLedger) Settle(requestID string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if _, ok := l.settled[requestID]; ok {
		l.DoubleCharge++
		return
	}
	cur, ok := l.open[requestID]
	if !ok {
		return
	}
	delete(l.open, requestID)
	cur.State = "settled"
	l.settled[requestID] = cur
}

func (l *MemLedger) OpenCount() int {
	l.mu.Lock()
	defer l.mu.Unlock()
	return len(l.open)
}

func (l *MemLedger) Snapshot() LedgerSnap {
	l.mu.Lock()
	defer l.mu.Unlock()
	cp := NewMemLedger()
	for k, v := range l.open {
		cp.open[k] = v
	}
	for k, v := range l.settled {
		cp.settled[k] = v
	}
	for k, v := range l.aborted {
		cp.aborted[k] = v
	}
	return LedgerSnap{TakenAt: time.Now(), Data: cp}
}

type LedgerSnap struct {
	TakenAt time.Time
	Data    *MemLedger
}

func RestoreLedger(snap LedgerSnap) *MemLedger {
	src := snap.Data
	out := NewMemLedger()
	if src == nil {
		return out
	}
	src.mu.Lock()
	defer src.mu.Unlock()
	for k, v := range src.open {
		out.open[k] = v
	}
	for k, v := range src.settled {
		out.settled[k] = v
	}
	for k, v := range src.aborted {
		out.aborted[k] = v
	}
	return out
}

package capacity

import (
	"context"
	"fmt"
	"sync"
)

// PGLedger persists reservations on PostgreSQL (SoR) and mirrors MemLedger counters.
type PGLedger struct {
	Inner    *MemLedger
	ExecSQL  func(sql string) error
	QuerySQL func(sql string) (string, error)
	mu       sync.Mutex
}

func (l *PGLedger) Reserve(ctx context.Context, requestID, projectID, keyID string, amount int64) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.ExecSQL == nil {
		return fmt.Errorf("postgres ledger not wired")
	}
	sql := fmt.Sprintf(
		`INSERT INTO ledger_entries(request_id, amount, state) VALUES (%s, %d, 'open')
		 ON CONFLICT (request_id) DO NOTHING`,
		pgLit(requestID), amount,
	)
	if err := l.ExecSQL(sql); err != nil {
		return err
	}
	return l.Inner.Reserve(ctx, requestID, projectID, keyID, amount)
}

func (l *PGLedger) Abort(ctx context.Context, requestID string) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.ExecSQL != nil {
		_ = l.ExecSQL(fmt.Sprintf(
			`UPDATE ledger_entries SET state='aborted' WHERE request_id=%s AND state='open'`,
			pgLit(requestID),
		))
	}
	return l.Inner.Abort(ctx, requestID)
}

func (l *PGLedger) Settle(requestID string) {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.ExecSQL != nil {
		if err := l.ExecSQL(fmt.Sprintf(
			`UPDATE ledger_entries SET state='settled' WHERE request_id=%s`,
			pgLit(requestID),
		)); err != nil {
			return
		}
	}
	l.Inner.Settle(requestID)
}

func pgLit(s string) string {
	out := "'"
	for _, r := range s {
		if r == '\'' {
			out += "''"
		} else {
			out += string(r)
		}
	}
	return out + "'"
}

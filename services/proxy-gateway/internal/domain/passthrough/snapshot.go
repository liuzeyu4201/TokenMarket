package passthrough

import (
	"context"
	"sync"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/score"
)

type snapshotCtxKey struct{}

// ProjectSnapshot is the trusted Project/binding view used for admit + routing.
// Mode and PreviewOptIn come from the authenticated Project record, never headers.
type ProjectSnapshot struct {
	ProjectID    string
	Mode         string
	PreviewOptIn bool
	BuyerOwnerID string
	Dedicated    DedicatedSnapshot
	QualifyReq   qualify.Request
	Candidates   []qualify.Candidate
	Signals      map[string]score.Signals
	Upstreams    map[string]Upstream
	Policy       score.Policy
	Seed         int64
}

// SnapshotStore is the Project/binding SoR the shipped kernel consults.
type SnapshotStore interface {
	Lookup(projectID string) (ProjectSnapshot, bool)
}

// MemoryStore is an in-process snapshot map (static env + tests + API cache).
type MemoryStore struct {
	mu sync.RWMutex
	m  map[string]ProjectSnapshot
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{m: map[string]ProjectSnapshot{}}
}

func (s *MemoryStore) Lookup(projectID string) (ProjectSnapshot, bool) {
	if s == nil || projectID == "" {
		return ProjectSnapshot{}, false
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	snap, ok := s.m[projectID]
	return snap, ok
}

func (s *MemoryStore) Put(snap ProjectSnapshot) {
	if s == nil || snap.ProjectID == "" {
		return
	}
	s.mu.Lock()
	if s.m == nil {
		s.m = map[string]ProjectSnapshot{}
	}
	s.m[snap.ProjectID] = snap
	s.mu.Unlock()
}

func WithSnapshot(ctx context.Context, snap ProjectSnapshot) context.Context {
	return context.WithValue(ctx, snapshotCtxKey{}, snap)
}

func SnapshotFrom(ctx context.Context) (ProjectSnapshot, bool) {
	if ctx == nil {
		return ProjectSnapshot{}, false
	}
	snap, ok := ctx.Value(snapshotCtxKey{}).(ProjectSnapshot)
	return snap, ok
}

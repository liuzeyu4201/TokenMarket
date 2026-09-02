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

// FetchingStore consults cache then a Project/Binding SoR. Missing SoR is fail-closed.
type FetchingStore struct {
	Cache SnapshotStore
	Fetch func(projectID string) (ProjectSnapshot, bool)
}

func (s *FetchingStore) Lookup(projectID string) (ProjectSnapshot, bool) {
	if projectID == "" {
		return ProjectSnapshot{}, false
	}
	if s != nil && s.Cache != nil {
		if snap, ok := s.Cache.Lookup(projectID); ok {
			return snap, true
		}
	}
	if s == nil || s.Fetch == nil {
		return ProjectSnapshot{}, false
	}
	snap, ok := s.Fetch(projectID)
	if !ok {
		return ProjectSnapshot{}, false
	}
	if put, ok := s.Cache.(interface{ Put(ProjectSnapshot) }); ok {
		put.Put(snap)
	}
	return snap, true
}

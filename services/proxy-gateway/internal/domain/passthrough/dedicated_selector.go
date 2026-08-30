package passthrough

import (
	"context"
	"sync"
)

// DedicatedSnapshot is one complete exclusive-binding view.
type DedicatedSnapshot struct {
	ConnectionID string
	Status       string
	Health       string
	Up           Upstream
	Draining     map[string]Upstream
}

// DedicatedSelector pins a dedicated Project to one Connection.
// It never consults a shared pool.
type DedicatedSelector struct {
	mu   sync.Mutex
	snap DedicatedSnapshot
}

func NewDedicatedSelector(snap DedicatedSnapshot) *DedicatedSelector {
	if snap.Draining == nil {
		snap.Draining = map[string]Upstream{}
	}
	return &DedicatedSelector{snap: snap}
}

func (s *DedicatedSelector) Replace(next DedicatedSnapshot) {
	if next.Draining == nil {
		next.Draining = map[string]Upstream{}
	}
	s.mu.Lock()
	s.snap = next
	s.mu.Unlock()
}

func (s *DedicatedSelector) Snapshot() DedicatedSnapshot {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := s.snap
	drain := make(map[string]Upstream, len(s.snap.Draining))
	for k, v := range s.snap.Draining {
		drain[k] = v
	}
	out.Draining = drain
	return out
}

func (s *DedicatedSelector) Select(_ context.Context, _, _ string) (Upstream, error) {
	snap := s.Snapshot()
	if snap.Status != "active" || snap.Health != "healthy" || snap.ConnectionID == "" {
		return Upstream{}, errDedicatedUnavailable
	}
	up := snap.Up
	up.ConnectionID = snap.ConnectionID
	return up, nil
}

func (s *DedicatedSelector) SelectConnection(_ context.Context, connectionID string) (Upstream, error) {
	snap := s.Snapshot()
	if connectionID != "" && connectionID == snap.ConnectionID {
		up := snap.Up
		up.ConnectionID = snap.ConnectionID
		return up, nil
	}
	if up, ok := snap.Draining[connectionID]; ok {
		up.ConnectionID = connectionID
		return up, nil
	}
	return Upstream{}, errDedicatedUnavailable
}

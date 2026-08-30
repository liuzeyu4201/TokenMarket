package passthrough

import (
	"context"
	"sync"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/score"
)

// ScoringSelector filters with SF23 then ranks with SF24.
type ScoringSelector struct {
	Request      qualify.Request
	Candidates   []qualify.Candidate
	Signals      map[string]score.Signals
	Policy       score.Policy
	Seed         int64
	Upstreams    map[string]Upstream
	LastFilter   qualify.Decision
	LastRank     []score.Row
	LastDecision score.Decision

	mu sync.Mutex
}

func (s *ScoringSelector) Select(_ context.Context, protocol, endpointID string) (Upstream, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	req := s.Request
	if req.Protocol == "" {
		req.Protocol = protocol
	}
	if req.Provider == "" {
		req.Provider = protocol
	}
	if req.EndpointID == "" {
		req.EndpointID = endpointID
	}
	s.LastFilter = qualify.Filter(req, s.Candidates)
	if len(s.LastFilter.QualifiedIDs) == 0 {
		s.LastRank = nil
		s.LastDecision = score.Decision{PolicyVersion: s.Policy.EffectiveVersion(), Seed: s.Seed}
		return Upstream{}, errNoUpstream
	}
	avail := make([]string, 0, len(s.LastFilter.QualifiedIDs))
	for _, id := range s.LastFilter.QualifiedIDs {
		if sig, ok := s.Signals[id]; ok && sig.CapacityPresent && sig.Remaining <= 0 {
			continue
		}
		avail = append(avail, id)
	}
	if len(avail) == 0 {
		s.LastRank = nil
		s.LastDecision = score.Decision{PolicyVersion: s.Policy.EffectiveVersion(), Seed: s.Seed}
		return Upstream{}, errNoUpstream
	}
	s.LastDecision = score.Decide(avail, s.Signals, s.Policy, s.Seed)
	s.LastRank = s.LastDecision.Rows
	id := s.LastDecision.Winner
	if id == "" {
		return Upstream{}, errNoUpstream
	}
	if sig, ok := s.Signals[id]; ok && sig.CapacityPresent {
		sig.Remaining--
		if sig.Remaining < 0 {
			sig.Remaining = 0
		}
		s.Signals[id] = sig
	}
	up, ok := s.Upstreams[id]
	if !ok {
		return Upstream{}, errNoUpstream
	}
	up.ConnectionID = id
	return up, nil
}

func (s *ScoringSelector) SelectConnection(_ context.Context, connectionID string) (Upstream, error) {
	up, ok := s.Upstreams[connectionID]
	if !ok {
		return Upstream{}, errNoUpstream
	}
	up.ConnectionID = connectionID
	return up, nil
}

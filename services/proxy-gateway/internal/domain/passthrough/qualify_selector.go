package passthrough

import (
	"context"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
)

// QualifyingSelector hard-filters shared candidates then picks the first ID.
type QualifyingSelector struct {
	Request    qualify.Request
	Candidates []qualify.Candidate
	Upstreams  map[string]Upstream
	Last       qualify.Decision
}

func (s *QualifyingSelector) Select(_ context.Context, protocol, endpointID string) (Upstream, error) {
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
	s.Last = qualify.Filter(req, s.Candidates)
	if len(s.Last.QualifiedIDs) == 0 {
		return Upstream{}, errNoUpstream
	}
	id := s.Last.QualifiedIDs[0]
	up, ok := s.Upstreams[id]
	if !ok {
		return Upstream{}, errNoUpstream
	}
	up.ConnectionID = id
	return up, nil
}

func (s *QualifyingSelector) SelectConnection(_ context.Context, connectionID string) (Upstream, error) {
	up, ok := s.Upstreams[connectionID]
	if !ok {
		return Upstream{}, errNoUpstream
	}
	up.ConnectionID = connectionID
	return up, nil
}

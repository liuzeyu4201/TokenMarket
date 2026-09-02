package passthrough

import (
	"context"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/qualify"
)

// QualifySelector is the shipped shared-pool path: SF23 hard filter then SF24 score.
type QualifySelector = ScoringSelector

// RoutingSelector picks dedicated fail-closed or shared qualify+score from the
// authenticated Project snapshot on the request context.
type RoutingSelector struct{}

func (RoutingSelector) Select(ctx context.Context, protocol, endpointID string) (Upstream, error) {
	snap, ok := SnapshotFrom(ctx)
	if !ok {
		return Upstream{}, errNoUpstream
	}
	switch snap.Mode {
	case "dedicated":
		return NewDedicatedSelector(snap.Dedicated).Select(ctx, protocol, endpointID)
	case "shared":
		sel := ScoringSelector{
			Request:    snap.qualifyRequest(protocol, endpointID),
			Candidates: snap.Candidates,
			Signals:    snap.Signals,
			Policy:     snap.Policy,
			Seed:       snap.Seed,
			Upstreams:  snap.Upstreams,
		}
		return sel.Select(ctx, protocol, endpointID)
	default:
		return Upstream{}, errNoUpstream
	}
}

func (RoutingSelector) SelectConnection(ctx context.Context, connectionID string) (Upstream, error) {
	snap, ok := SnapshotFrom(ctx)
	if !ok {
		return Upstream{}, errNoUpstream
	}
	if snap.Mode == "dedicated" {
		return NewDedicatedSelector(snap.Dedicated).SelectConnection(ctx, connectionID)
	}
	sel := ScoringSelector{Upstreams: snap.Upstreams}
	return sel.SelectConnection(ctx, connectionID)
}

func (s ProjectSnapshot) qualifyRequest(protocol, endpointID string) qualify.Request {
	req := s.QualifyReq
	if req.Protocol == "" {
		req.Protocol = protocol
	}
	if req.Provider == "" {
		req.Provider = protocol
	}
	if req.EndpointID == "" {
		req.EndpointID = endpointID
	}
	if req.ProjectMode == "" {
		req.ProjectMode = s.Mode
	}
	if req.BuyerOwnerID == "" {
		req.BuyerOwnerID = s.BuyerOwnerID
	}
	return req
}

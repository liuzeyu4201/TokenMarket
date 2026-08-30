package passthrough

import "context"

// Upstream is the decrypted target for one native request.
type Upstream struct {
	BaseURL      string
	Credential   string
	ConnectionID string
}

// Selector picks an upstream for a protocol+endpoint. SF23 supplies routing.
// SelectConnection pins a follow-up resource request to a stored Connection.
type Selector interface {
	Select(ctx context.Context, protocol, endpointID string) (Upstream, error)
	SelectConnection(ctx context.Context, connectionID string) (Upstream, error)
}

// StaticSelector returns a fixed upstream (tests).
type StaticSelector struct {
	Up Upstream
}

func (s StaticSelector) Select(context.Context, string, string) (Upstream, error) {
	return s.Up, nil
}

func (s StaticSelector) SelectConnection(_ context.Context, connectionID string) (Upstream, error) {
	if s.Up.ConnectionID != "" && connectionID != "" && s.Up.ConnectionID != connectionID {
		return Upstream{}, errNoUpstream
	}
	up := s.Up
	if up.ConnectionID == "" {
		up.ConnectionID = connectionID
	}
	return up, nil
}

// FailClosedSelector always yields no upstream.
type FailClosedSelector struct{}

func (FailClosedSelector) Select(context.Context, string, string) (Upstream, error) {
	return Upstream{}, errNoUpstream
}

func (FailClosedSelector) SelectConnection(context.Context, string) (Upstream, error) {
	return Upstream{}, errNoUpstream
}

type selectorError string

func (e selectorError) Error() string { return string(e) }

const errNoUpstream selectorError = CodeNoUpstream

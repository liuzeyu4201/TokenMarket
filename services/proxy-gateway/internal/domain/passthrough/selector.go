package passthrough

import "context"

// Upstream is the decrypted target for one native request.
type Upstream struct {
	BaseURL    string
	Credential string
}

// Selector picks an upstream for a protocol+endpoint. SF23 supplies routing.
type Selector interface {
	Select(ctx context.Context, protocol, endpointID string) (Upstream, error)
}

// StaticSelector returns a fixed upstream (tests).
type StaticSelector struct {
	Up Upstream
}

func (s StaticSelector) Select(context.Context, string, string) (Upstream, error) {
	return s.Up, nil
}

// FailClosedSelector always yields no upstream.
type FailClosedSelector struct{}

func (FailClosedSelector) Select(context.Context, string, string) (Upstream, error) {
	return Upstream{}, errNoUpstream
}

type selectorError string

func (e selectorError) Error() string { return string(e) }

const errNoUpstream selectorError = CodeNoUpstream

// Package usageobs SF17 完成观察端口（网关侧，不落账）。
package usageobs

import "context"

// Observation 单次请求完成观察。
type Observation struct {
	RequestID        string
	ProxyKeyID       string
	APIKeyID         string
	BuyerID          string
	SellerID         string
	Platform         string
	Model            string
	PromptTokens     *int
	CompletionTokens *int
	TotalTokens      *int
	UsageSource      string
	Partial          bool
	LatencyMS        int64
	StatusCode       int
	EndReason        string
}

// Sink 幂等按 RequestID。
type Sink interface {
	Observe(ctx context.Context, obs Observation) error
}

// MemorySink 进程内幂等槽，测试与本地默认。
type MemorySink struct {
	byID map[string]Observation
}

func NewMemorySink() *MemorySink {
	return &MemorySink{byID: map[string]Observation{}}
}

func (m *MemorySink) Observe(_ context.Context, obs Observation) error {
	if m.byID == nil {
		m.byID = map[string]Observation{}
	}
	if obs.RequestID == "" {
		return nil
	}
	if _, ok := m.byID[obs.RequestID]; ok {
		return nil
	}
	m.byID[obs.RequestID] = obs
	return nil
}

func (m *MemorySink) Get(id string) (Observation, bool) {
	o, ok := m.byID[id]
	return o, ok
}

func (m *MemorySink) Len() int { return len(m.byID) }

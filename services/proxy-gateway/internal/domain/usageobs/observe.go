// Package usageobs SF17 完成观察端口（网关侧，不落账）。
package usageobs

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"sync"
)

// ErrConflict 同一服务端事件 ID 带有冲突载荷；不得覆盖或删除既有记录。
var ErrConflict = errors.New("usage observation conflict")

// Observation 单次请求完成观察。
type Observation struct {
	RequestID        string
	ClientRequestID  string
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

// NewEventID 返回服务端拥有的用量事件 ID（与客户端 X-Request-ID 无关）。
func NewEventID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return ""
	}
	return hex.EncodeToString(b)
}

// Sink 幂等按 RequestID（服务端事件 ID）。
type Sink interface {
	Observe(ctx context.Context, obs Observation) error
}

// MemorySink 进程内幂等槽，测试与本地默认。
type MemorySink struct {
	mu   sync.Mutex
	byID map[string]Observation
}

func NewMemorySink() *MemorySink {
	return &MemorySink{byID: map[string]Observation{}}
}

func (m *MemorySink) Observe(_ context.Context, obs Observation) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.byID == nil {
		m.byID = map[string]Observation{}
	}
	if obs.RequestID == "" {
		return nil
	}
	if existing, ok := m.byID[obs.RequestID]; ok {
		if observationsConflict(existing, obs) {
			return ErrConflict
		}
		return nil
	}
	m.byID[obs.RequestID] = obs
	return nil
}

func (m *MemorySink) Get(id string) (Observation, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	o, ok := m.byID[id]
	return o, ok
}

func (m *MemorySink) Len() int {
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.byID)
}

func (m *MemorySink) All() []Observation {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]Observation, 0, len(m.byID))
	for _, o := range m.byID {
		out = append(out, o)
	}
	return out
}

func observationsConflict(a, b Observation) bool {
	return a.Platform != b.Platform ||
		a.Model != b.Model ||
		a.UsageSource != b.UsageSource ||
		intPtrVal(a.TotalTokens) != intPtrVal(b.TotalTokens) ||
		intPtrVal(a.PromptTokens) != intPtrVal(b.PromptTokens) ||
		intPtrVal(a.CompletionTokens) != intPtrVal(b.CompletionTokens)
}

func intPtrVal(p *int) int {
	if p == nil {
		return -1
	}
	return *p
}

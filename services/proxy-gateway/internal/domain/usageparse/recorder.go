package usageparse

import "sync"

// Recorder stores captures idempotently by request_id.
type Recorder interface {
	Record(Capture)
}

// Memory is a process-local recorder for tests and local default.
type Memory struct {
	mu sync.Mutex
	by map[string]Capture
	n  int
}

func NewMemory() *Memory {
	return &Memory{by: map[string]Capture{}}
}

func (m *Memory) Record(c Capture) {
	if m == nil {
		return
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.by == nil {
		m.by = map[string]Capture{}
	}
	m.n++
	if c.RequestID == "" {
		m.by[""] = c
		return
	}
	if _, ok := m.by[c.RequestID]; ok {
		return
	}
	m.by[c.RequestID] = c
}

func (m *Memory) Get(id string) (Capture, bool) {
	if m == nil {
		return Capture{}, false
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	c, ok := m.by[id]
	return c, ok
}

func (m *Memory) Len() int {
	if m == nil {
		return 0
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	return len(m.by)
}

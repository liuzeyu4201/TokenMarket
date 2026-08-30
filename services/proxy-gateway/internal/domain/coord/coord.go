package coord

import (
	"errors"
	"strings"
	"sync"
	"time"
)

var ErrUnavailable = errors.New("coordination store unavailable")

// Dimension 容量键维度。
type Dimension string

const (
	DimKey        Dimension = "key"
	DimProject    Dimension = "project"
	DimConnection Dimension = "connection"
	DimProtocol   Dimension = "protocol"
)

type Backend interface {
	Incr(slot string, limit int, ttl time.Duration) (bool, error)
	Decr(slot string) error
	Occupy(connectionID, projectID string) (bool, error)
	ReleaseOccupy(connectionID, projectID string) error
	Occupant(connectionID string) (string, bool, error)
	SetEpoch(keyID string, epoch uint64) error
	Epoch(keyID string) (uint64, error)
}

// Memory 原子内存后端（可重建缓存语义；进程内 race 测试与单节点默认）。
type Memory struct {
	mu       sync.Mutex
	fail     bool
	counts   map[string]int
	occupant map[string]string
	epoch    map[string]uint64
}

func NewMemory() *Memory {
	return &Memory{
		counts:   map[string]int{},
		occupant: map[string]string{},
		epoch:    map[string]uint64{},
	}
}

func (m *Memory) SetUnavailable(v bool) { m.fail = v }

func (m *Memory) check() error {
	if m == nil || m.fail {
		return ErrUnavailable
	}
	return nil
}

func (m *Memory) Incr(slot string, limit int, _ time.Duration) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if err := m.check(); err != nil {
		return false, err
	}
	if limit < 1 {
		return false, nil
	}
	if m.counts[slot] >= limit {
		return false, nil
	}
	m.counts[slot]++
	return true, nil
}

func (m *Memory) Decr(slot string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if err := m.check(); err != nil {
		return err
	}
	if m.counts[slot] > 0 {
		m.counts[slot]--
	}
	return nil
}

func (m *Memory) Occupy(connectionID, projectID string) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if err := m.check(); err != nil {
		return false, err
	}
	if cur, ok := m.occupant[connectionID]; ok {
		return cur == projectID, nil
	}
	m.occupant[connectionID] = projectID
	return true, nil
}

func (m *Memory) ReleaseOccupy(connectionID, projectID string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if err := m.check(); err != nil {
		return err
	}
	if cur, ok := m.occupant[connectionID]; ok && cur == projectID {
		delete(m.occupant, connectionID)
	}
	return nil
}

func (m *Memory) Occupant(connectionID string) (string, bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if err := m.check(); err != nil {
		return "", false, err
	}
	v, ok := m.occupant[connectionID]
	return v, ok, nil
}

func (m *Memory) SetEpoch(keyID string, epoch uint64) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if err := m.check(); err != nil {
		return err
	}
	if epoch > m.epoch[keyID] {
		m.epoch[keyID] = epoch
	}
	return nil
}

func (m *Memory) Epoch(keyID string) (uint64, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if err := m.check(); err != nil {
		return 0, err
	}
	return m.epoch[keyID], nil
}

// Coordinator 对外 API。
type Coordinator struct {
	b Backend
}

func New(b Backend) *Coordinator { return &Coordinator{b: b} }

func Slot(dim Dimension, id string) string {
	return string(dim) + ":" + strings.TrimSpace(id)
}

func (c *Coordinator) TryCapacity(dim Dimension, id string, limit int) (bool, error) {
	if c == nil || c.b == nil {
		return false, ErrUnavailable
	}
	ok, err := c.b.Incr(Slot(dim, id), limit, time.Minute)
	if err != nil {
		return false, err
	}
	return ok, nil
}

func (c *Coordinator) ReleaseCapacity(dim Dimension, id string) error {
	if c == nil || c.b == nil {
		return ErrUnavailable
	}
	return c.b.Decr(Slot(dim, id))
}

func (c *Coordinator) TryDedicated(connectionID, projectID string) (bool, error) {
	if c == nil || c.b == nil {
		return false, ErrUnavailable
	}
	return c.b.Occupy(connectionID, projectID)
}

func (c *Coordinator) ReleaseDedicated(connectionID, projectID string) error {
	if c == nil || c.b == nil {
		return ErrUnavailable
	}
	return c.b.ReleaseOccupy(connectionID, projectID)
}

func (c *Coordinator) Occupant(connectionID string) (string, bool, error) {
	if c == nil || c.b == nil {
		return "", false, ErrUnavailable
	}
	return c.b.Occupant(connectionID)
}

func (c *Coordinator) AllowKey(keyID string, knownEpoch uint64) (bool, error) {
	if c == nil || c.b == nil {
		return false, ErrUnavailable
	}
	ep, err := c.b.Epoch(keyID)
	if err != nil {
		return false, err
	}
	return knownEpoch >= ep, nil
}

func (c *Coordinator) RevokeKey(keyID string, epoch uint64) error {
	if c == nil || c.b == nil {
		return ErrUnavailable
	}
	return c.b.SetEpoch(keyID, epoch)
}

// RebuildOccupancy 从权威绑定重建；热状态先清空再写入，不得额外发明占用。
func (c *Coordinator) RebuildOccupancy(bindings map[string]string) error {
	if c == nil || c.b == nil {
		return ErrUnavailable
	}
	mem, ok := c.b.(*Memory)
	if !ok {
		return ErrUnavailable
	}
	mem.mu.Lock()
	defer mem.mu.Unlock()
	if mem.fail {
		return ErrUnavailable
	}
	mem.occupant = map[string]string{}
	for conn, project := range bindings {
		mem.occupant[conn] = project
	}
	return nil
}

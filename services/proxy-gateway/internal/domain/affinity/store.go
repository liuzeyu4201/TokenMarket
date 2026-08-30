// Package affinity maps vendor resource IDs to the Connection that created them.
package affinity

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sync"
)

var (
	ErrNotFound = errors.New("AFFINITY_NOT_FOUND")
	ErrConflict = errors.New("AFFINITY_CONFLICT")
)

// Binding is one (protocol, resource_id) → Connection mapping.
type Binding struct {
	Protocol     string `json:"protocol"`
	ResourceID   string `json:"resource_id"`
	ConnectionID string `json:"connection_id"`
	ProjectID    string `json:"project_id,omitempty"`
	EndpointID   string `json:"endpoint_id,omitempty"`
}

// Store is the fail-closed affinity table.
type Store interface {
	Put(Binding) error
	Get(protocol, resourceID string) (Binding, error)
}

// Table is an in-process store with optional JSON snapshot persistence.
type Table struct {
	mu   sync.Mutex
	m    map[string]Binding
	path string
}

// NewTable loads an optional snapshot file (IDs and connection refs only).
func NewTable(snapshotPath string) *Table {
	t := &Table{m: map[string]Binding{}, path: snapshotPath}
	t.load()
	return t
}

func key(protocol, resourceID string) string {
	return protocol + "\x00" + resourceID
}

func (t *Table) Put(b Binding) error {
	if t == nil {
		return ErrNotFound
	}
	if b.Protocol == "" || b.ResourceID == "" || b.ConnectionID == "" {
		return ErrNotFound
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.m == nil {
		t.m = map[string]Binding{}
	}
	k := key(b.Protocol, b.ResourceID)
	if existing, ok := t.m[k]; ok {
		if existing.ConnectionID != b.ConnectionID {
			return ErrConflict
		}
		return nil
	}
	t.m[k] = b
	return t.persistLocked()
}

func (t *Table) Get(protocol, resourceID string) (Binding, error) {
	if t == nil {
		return Binding{}, ErrNotFound
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	b, ok := t.m[key(protocol, resourceID)]
	if !ok {
		return Binding{}, ErrNotFound
	}
	return b, nil
}

func (t *Table) persistLocked() error {
	if t.path == "" {
		return nil
	}
	out := make([]Binding, 0, len(t.m))
	for _, b := range t.m {
		out = append(out, b)
	}
	raw, err := json.Marshal(out)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(t.path), 0o700); err != nil {
		return err
	}
	tmp := t.path + ".tmp"
	if err := os.WriteFile(tmp, raw, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, t.path)
}

func (t *Table) load() {
	if t.path == "" {
		return
	}
	raw, err := os.ReadFile(t.path)
	if err != nil {
		return
	}
	var list []Binding
	if json.Unmarshal(raw, &list) != nil {
		return
	}
	t.m = make(map[string]Binding, len(list))
	for _, b := range list {
		if b.Protocol == "" || b.ResourceID == "" || b.ConnectionID == "" {
			continue
		}
		t.m[key(b.Protocol, b.ResourceID)] = b
	}
}

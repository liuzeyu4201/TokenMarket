package usageoutbox

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"
)

var (
	ErrUnavailable = errors.New("usage outbox unavailable")
	ErrConflict    = errors.New("usage outbox event conflict")
	ErrForbidden   = errors.New("usage outbox payload contains forbidden fields")
)

const SchemaVersion = "1.0.0"

var forbidden = []string{"api_key", "authorization", "raw_body", "credential", "otp"}

type Event struct {
	EventID         string `json:"event_id"`
	RequestID       string `json:"request_id"`
	Seq             int    `json:"seq"`
	Type            string `json:"type"`
	Version         string `json:"version"`
	Timestamp       string `json:"timestamp"`
	Producer        string `json:"producer"`
	CorrelationID   string `json:"correlation_id"`
	ProjectID       string `json:"project_id,omitempty"`
	ConnectionID    string `json:"connection_id,omitempty"`
	CatalogMajor    int    `json:"catalog_major"`
	PricingVersion  string `json:"pricing_version,omitempty"`
	RouteDecisionID string `json:"route_decision_id,omitempty"`
	Protocol        string `json:"protocol,omitempty"`
	EndpointID      string `json:"endpoint_id,omitempty"`
	Status          string `json:"status"`
	EvidenceDigest  string `json:"evidence_digest,omitempty"`
}

type record struct {
	Event      Event  `json:"event"`
	Attempts   int    `json:"attempts"`
	DeadLetter bool   `json:"dead_letter"`
	LastError  string `json:"last_error,omitempty"`
	Done       bool   `json:"done"`
}

type FileStore struct {
	dir     string
	maxFail int
	mu      sync.Mutex
}

func NewFileStore(dir string, maxFail int) (*FileStore, error) {
	if dir == "" {
		return nil, ErrUnavailable
	}
	if maxFail < 1 {
		maxFail = 3
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	return &FileStore{dir: dir, maxFail: maxFail}, nil
}

func Validate(ev Event) error {
	if ev.EventID == "" || ev.RequestID == "" || ev.Seq < 1 || ev.Status == "" || ev.CatalogMajor < 1 {
		return fmt.Errorf("incomplete event")
	}
	raw, _ := json.Marshal(ev)
	var generic map[string]any
	if err := json.Unmarshal(raw, &generic); err != nil {
		return err
	}
	for _, k := range forbidden {
		if _, ok := generic[k]; ok {
			return ErrForbidden
		}
	}
	return nil
}

func Digest(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:8])
}

func (s *FileStore) path(id string) string {
	return filepath.Join(s.dir, id+".json")
}

func (s *FileStore) Append(ev Event) error {
	if s == nil {
		return ErrUnavailable
	}
	if ev.Version == "" {
		ev.Version = SchemaVersion
	}
	if ev.Timestamp == "" {
		ev.Timestamp = time.Now().UTC().Format(time.RFC3339)
	}
	if ev.Producer == "" {
		ev.Producer = "proxy-gateway"
	}
	if ev.Type == "" {
		ev.Type = "usage.lifecycle"
	}
	if err := Validate(ev); err != nil {
		return err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	p := s.path(ev.EventID)
	if b, err := os.ReadFile(p); err == nil {
		var existing record
		if json.Unmarshal(b, &existing) == nil {
			if existing.Event.RequestID != ev.RequestID || existing.Event.Seq != ev.Seq {
				return ErrConflict
			}
			return nil
		}
	}
	rec := record{Event: ev}
	b, err := json.Marshal(rec)
	if err != nil {
		return err
	}
	tmp := p + ".tmp"
	if err := os.WriteFile(tmp, b, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, p)
}

func (s *FileStore) loadAll() ([]record, error) {
	ents, err := os.ReadDir(s.dir)
	if err != nil {
		return nil, err
	}
	var out []record
	for _, e := range ents {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		b, err := os.ReadFile(filepath.Join(s.dir, e.Name()))
		if err != nil {
			return nil, err
		}
		var rec record
		if err := json.Unmarshal(b, &rec); err != nil {
			return nil, err
		}
		out = append(out, rec)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Event.RequestID == out[j].Event.RequestID {
			return out[i].Event.Seq < out[j].Event.Seq
		}
		return out[i].Event.RequestID < out[j].Event.RequestID
	})
	return out, nil
}

func (s *FileStore) save(rec record) error {
	b, err := json.Marshal(rec)
	if err != nil {
		return err
	}
	p := s.path(rec.Event.EventID)
	tmp := p + ".tmp"
	if err := os.WriteFile(tmp, b, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, p)
}

type Handler func(Event) error

func (s *FileStore) Drain(h Handler) error {
	if s == nil {
		return ErrUnavailable
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	recs, err := s.loadAll()
	if err != nil {
		return err
	}
	for _, rec := range recs {
		if rec.Done || rec.DeadLetter {
			continue
		}
		if err := h(rec.Event); err != nil {
			rec.Attempts++
			rec.LastError = err.Error()
			if rec.Attempts >= s.maxFail {
				rec.DeadLetter = true
			}
		} else {
			rec.Done = true
			rec.LastError = ""
		}
		if err := s.save(rec); err != nil {
			return err
		}
	}
	return nil
}

func (s *FileStore) DeadLetters() ([]Event, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	recs, err := s.loadAll()
	if err != nil {
		return nil, err
	}
	var out []Event
	for _, rec := range recs {
		if rec.DeadLetter && !rec.Done {
			out = append(out, rec.Event)
		}
	}
	return out, nil
}

func (s *FileStore) ReplayDeadLetter(eventID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	b, err := os.ReadFile(s.path(eventID))
	if err != nil {
		return err
	}
	var rec record
	if err := json.Unmarshal(b, &rec); err != nil {
		return err
	}
	rec.DeadLetter = false
	rec.Attempts = 0
	return s.save(rec)
}

// IdempotentCounter 证明重复投递效果一次。
type IdempotentCounter struct {
	mu    sync.Mutex
	seen  map[string]struct{}
	Count int
}

func (c *IdempotentCounter) Handle(ev Event) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.seen == nil {
		c.seen = map[string]struct{}{}
	}
	if _, ok := c.seen[ev.EventID]; ok {
		return nil
	}
	c.seen[ev.EventID] = struct{}{}
	c.Count++
	return nil
}

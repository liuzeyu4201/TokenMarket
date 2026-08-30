package affinity_test

import (
	"errors"
	"path/filepath"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/affinity"
)

func TestPutGetRoundTrip(t *testing.T) {
	s := affinity.NewTable("")
	b := affinity.Binding{Protocol: "openai", ResourceID: "file-1", ConnectionID: "conn-A", ProjectID: "p1"}
	if err := s.Put(b); err != nil {
		t.Fatal(err)
	}
	got, err := s.Get("openai", "file-1")
	if err != nil {
		t.Fatal(err)
	}
	if got.ConnectionID != "conn-A" || got.ProjectID != "p1" {
		t.Fatalf("%+v", got)
	}
}

func TestGetMissing(t *testing.T) {
	s := affinity.NewTable("")
	_, err := s.Get("openai", "missing")
	if !errors.Is(err, affinity.ErrNotFound) {
		t.Fatalf("%v", err)
	}
}

func TestPutConflict(t *testing.T) {
	s := affinity.NewTable("")
	b := affinity.Binding{Protocol: "openai", ResourceID: "file-1", ConnectionID: "conn-A"}
	if err := s.Put(b); err != nil {
		t.Fatal(err)
	}
	err := s.Put(affinity.Binding{Protocol: "openai", ResourceID: "file-1", ConnectionID: "conn-B"})
	if !errors.Is(err, affinity.ErrConflict) {
		t.Fatalf("%v", err)
	}
	got, _ := s.Get("openai", "file-1")
	if got.ConnectionID != "conn-A" {
		t.Fatalf("overwrote mapping %+v", got)
	}
}

func TestPutIdempotentSameConnection(t *testing.T) {
	s := affinity.NewTable("")
	b := affinity.Binding{Protocol: "anthropic", ResourceID: "file-9", ConnectionID: "c1"}
	if err := s.Put(b); err != nil {
		t.Fatal(err)
	}
	if err := s.Put(b); err != nil {
		t.Fatal(err)
	}
}

func TestSnapshotSurvivesRestart(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "affinity.json")
	s1 := affinity.NewTable(p)
	if err := s1.Put(affinity.Binding{Protocol: "openai", ResourceID: "file-1", ConnectionID: "conn-A"}); err != nil {
		t.Fatal(err)
	}
	s2 := affinity.NewTable(p)
	got, err := s2.Get("openai", "file-1")
	if err != nil {
		t.Fatal(err)
	}
	if got.ConnectionID != "conn-A" {
		t.Fatalf("%+v", got)
	}
}

func TestNilTableFailClosed(t *testing.T) {
	var s *affinity.Table
	if err := s.Put(affinity.Binding{Protocol: "openai", ResourceID: "x", ConnectionID: "c"}); !errors.Is(err, affinity.ErrNotFound) {
		t.Fatalf("%v", err)
	}
	if _, err := s.Get("openai", "x"); !errors.Is(err, affinity.ErrNotFound) {
		t.Fatalf("%v", err)
	}
}

package usageobs_test

import (
	"context"
	"os"
	"sync"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageobs"
)

func TestMemorySinkIdempotentByRequestID(t *testing.T) {
	s := usageobs.NewMemorySink()
	a := usageobs.Observation{RequestID: "r1", TotalTokens: intPtr(3), UsageSource: "official"}
	b := usageobs.Observation{RequestID: "r1", TotalTokens: intPtr(3), UsageSource: "official"}
	if err := s.Observe(context.Background(), a); err != nil {
		t.Fatal(err)
	}
	if err := s.Observe(context.Background(), b); err != nil {
		t.Fatal(err)
	}
	got, ok := s.Get("r1")
	if !ok || got.TotalTokens == nil || *got.TotalTokens != 3 {
		t.Fatalf("%+v", got)
	}
	if s.Len() != 1 {
		t.Fatal(s.Len())
	}
	conflict := usageobs.Observation{RequestID: "r1", TotalTokens: intPtr(9), UsageSource: "official"}
	if err := s.Observe(context.Background(), conflict); err == nil {
		t.Fatal("conflict")
	}
}

func intPtr(n int) *int { return &n }

func TestDurableSinkWritesThenRemovesOnSuccess(t *testing.T) {
	dir := t.TempDir()
	mem := usageobs.NewMemorySink()
	d := &usageobs.DurableSink{Dir: dir, Next: mem}
	obs := usageobs.Observation{RequestID: "rid-1", UsageSource: "official"}
	if err := d.Observe(context.Background(), obs); err != nil {
		t.Fatal(err)
	}
	if mem.Len() != 1 {
		t.Fatal(mem.Len())
	}
	ents, _ := os.ReadDir(dir)
	if len(ents) != 0 {
		t.Fatalf("wal leftover %d", len(ents))
	}
}

type failSink struct{}

func (failSink) Observe(context.Context, usageobs.Observation) error {
	return errBoom
}

var errBoom = errString("boom")

type errString string

func (e errString) Error() string { return string(e) }

func TestMemoryObserveEmptyIDAndNilMap(t *testing.T) {
	s := &usageobs.MemorySink{}
	if err := s.Observe(context.Background(), usageobs.Observation{}); err != nil {
		t.Fatal(err)
	}
	if s.Len() != 0 {
		t.Fatal(s.Len())
	}
}

func TestDurableNilAndReplayEmpty(t *testing.T) {
	var d *usageobs.DurableSink
	if err := d.Observe(context.Background(), usageobs.Observation{RequestID: "x"}); err != nil {
		t.Fatal(err)
	}
	if n := d.Replay(context.Background()); n != 0 {
		t.Fatal(n)
	}
	empty := &usageobs.DurableSink{Dir: t.TempDir() + "/missing", Next: usageobs.NewMemorySink()}
	if n := empty.Replay(context.Background()); n != 0 {
		t.Fatal(n)
	}
}

func TestMemorySinkConcurrentObserveNoRace(t *testing.T) {
	s := usageobs.NewMemorySink()
	var wg sync.WaitGroup
	for i := 0; i < 32; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			id := usageobs.NewEventID()
			_ = s.Observe(context.Background(), usageobs.Observation{RequestID: id, UsageSource: "official"})
		}(i)
	}
	wg.Wait()
	if s.Len() != 32 {
		t.Fatalf("len %d", s.Len())
	}
}

func TestIdenticalEventIsExactlyOnceAndConflictPreservesWAL(t *testing.T) {
	dir := t.TempDir()
	mem := usageobs.NewMemorySink()
	d := &usageobs.DurableSink{Dir: dir, Next: mem}
	tok := 3
	obs := usageobs.Observation{RequestID: "evt-1", UsageSource: "official", TotalTokens: &tok, Platform: "volcano", Model: "m"}
	if err := d.Observe(context.Background(), obs); err != nil {
		t.Fatal(err)
	}
	if err := d.Observe(context.Background(), obs); err != nil {
		t.Fatal(err)
	}
	if mem.Len() != 1 {
		t.Fatal(mem.Len())
	}
	ents, _ := os.ReadDir(dir)
	if len(ents) != 0 {
		t.Fatalf("identical replay leftover wal %d", len(ents))
	}
	other := 9
	conflict := obs
	conflict.TotalTokens = &other
	if err := d.Observe(context.Background(), conflict); err == nil {
		t.Fatal("expected conflict")
	}
	ents, _ = os.ReadDir(dir)
	if len(ents) != 1 {
		t.Fatalf("conflicting wal should remain, got %d", len(ents))
	}
	if mem.Len() != 1 {
		t.Fatal("must not delete or replace first observation")
	}
	got, _ := mem.Get("evt-1")
	if got.TotalTokens == nil || *got.TotalTokens != 3 {
		t.Fatalf("%+v", got)
	}
}

func TestDurableReplayAfterFailure(t *testing.T) {
	dir := t.TempDir()
	d := &usageobs.DurableSink{Dir: dir, Next: failSink{}}
	_ = d.Observe(context.Background(), usageobs.Observation{RequestID: "rid-2"})
	ents, _ := os.ReadDir(dir)
	if len(ents) != 1 {
		t.Fatalf("want wal file got %d", len(ents))
	}
	ok := usageobs.NewMemorySink()
	d.Next = ok
	if n := d.Replay(context.Background()); n != 1 {
		t.Fatalf("replay %d", n)
	}
	if ok.Len() != 1 {
		t.Fatal(ok.Len())
	}
}

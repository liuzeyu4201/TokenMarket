package usageobs_test

import (
	"context"
	"os"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageobs"
)

func TestMemorySinkIdempotentByRequestID(t *testing.T) {
	s := usageobs.NewMemorySink()
	a := usageobs.Observation{RequestID: "r1", TotalTokens: intPtr(3), UsageSource: "official"}
	b := usageobs.Observation{RequestID: "r1", TotalTokens: intPtr(9), UsageSource: "official"}
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

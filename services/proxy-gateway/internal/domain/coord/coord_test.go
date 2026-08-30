package coord_test

import (
	"sync"
	"sync/atomic"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/coord"
)

func TestDedicatedOccupyOnlyOneWinner(t *testing.T) {
	c := coord.New(coord.NewMemory())
	var wins atomic.Int32
	var wg sync.WaitGroup
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			ok, err := c.TryDedicated("conn-1", "project-"+string(rune('A'+i)))
			if err != nil {
				t.Errorf("err %v", err)
				return
			}
			if ok {
				wins.Add(1)
			}
		}(i)
	}
	wg.Wait()
	if wins.Load() != 1 {
		t.Fatalf("wins %d want 1", wins.Load())
	}
}

func TestCapacityAtomicLimit(t *testing.T) {
	c := coord.New(coord.NewMemory())
	var okN atomic.Int32
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ok, err := c.TryCapacity(coord.DimKey, "k1", 5)
			if err != nil {
				t.Errorf("%v", err)
				return
			}
			if ok {
				okN.Add(1)
			}
		}()
	}
	wg.Wait()
	if okN.Load() != 5 {
		t.Fatalf("ok %d want 5", okN.Load())
	}
	if err := c.ReleaseCapacity(coord.DimKey, "k1"); err != nil {
		t.Fatal(err)
	}
	if err := c.ReleaseCapacity(coord.DimKey, "k1"); err != nil {
		t.Fatal(err)
	}
	// extra releases must not go negative (still can acquire up to remaining+released)
	ok, err := c.TryCapacity(coord.DimKey, "k1", 5)
	if err != nil || !ok {
		t.Fatalf("after release want capacity err=%v ok=%v", err, ok)
	}
}

func TestRevokeAndFailClosed(t *testing.T) {
	mem := coord.NewMemory()
	c := coord.New(mem)
	ok, err := c.AllowKey("key-1", 0)
	if err != nil || !ok {
		t.Fatalf("fresh key err=%v ok=%v", err, ok)
	}
	if err := c.RevokeKey("key-1", 3); err != nil {
		t.Fatal(err)
	}
	ok, err = c.AllowKey("key-1", 2)
	if err != nil || ok {
		t.Fatalf("stale epoch should deny err=%v ok=%v", err, ok)
	}
	ok, err = c.AllowKey("key-1", 3)
	if err != nil || !ok {
		t.Fatalf("current epoch should allow err=%v ok=%v", err, ok)
	}
	mem.SetUnavailable(true)
	ok, err = c.AllowKey("key-1", 9)
	if err == nil || ok {
		t.Fatalf("unavailable must fail closed err=%v ok=%v", err, ok)
	}
	ok, err = c.TryDedicated("c", "p")
	if err == nil || ok {
		t.Fatalf("occupy fail closed err=%v ok=%v", err, ok)
	}
}

func TestRebuildDoesNotInventOccupancy(t *testing.T) {
	c := coord.New(coord.NewMemory())
	ok, err := c.TryDedicated("conn-a", "proj-a")
	if err != nil || !ok {
		t.Fatal(err, ok)
	}
	if err := c.RebuildOccupancy(map[string]string{"conn-b": "proj-b"}); err != nil {
		t.Fatal(err)
	}
	_, hasA, err := c.Occupant("conn-a")
	if err != nil {
		t.Fatal(err)
	}
	if hasA {
		t.Fatal("stale occupancy leaked")
	}
	who, hasB, err := c.Occupant("conn-b")
	if err != nil || !hasB || who != "proj-b" {
		t.Fatalf("rebuild occupant=%s has=%v err=%v", who, hasB, err)
	}
}

func TestReleaseDedicatedAndNilCoordinator(t *testing.T) {
	c := coord.New(coord.NewMemory())
	ok, err := c.TryDedicated("conn-z", "p1")
	if err != nil || !ok {
		t.Fatal(err, ok)
	}
	if err := c.ReleaseDedicated("conn-z", "p1"); err != nil {
		t.Fatal(err)
	}
	if err := c.ReleaseDedicated("conn-z", "p1"); err != nil {
		t.Fatal(err)
	}
	ok, err = c.TryDedicated("conn-z", "p2")
	if err != nil || !ok {
		t.Fatalf("reoccupy after release err=%v ok=%v", err, ok)
	}
	var n *coord.Coordinator
	if _, err := n.TryDedicated("c", "p"); err == nil {
		t.Fatal("nil coord")
	}
	if _, err := n.AllowKey("k", 0); err == nil {
		t.Fatal("nil allow")
	}
	if err := n.RevokeKey("k", 1); err == nil {
		t.Fatal("nil revoke")
	}
	if err := n.ReleaseCapacity(coord.DimProtocol, "openai"); err == nil {
		t.Fatal("nil release cap")
	}
	if _, err := n.TryCapacity(coord.DimProject, "p", 1); err == nil {
		t.Fatal("nil cap")
	}
	if _, _, err := n.Occupant("x"); err == nil {
		t.Fatal("nil occupant")
	}
	if err := n.RebuildOccupancy(nil); err == nil {
		t.Fatal("nil rebuild")
	}
	if coord.Slot(coord.DimConnection, " id ") != "connection:id" {
		t.Fatal(coord.Slot(coord.DimConnection, " id "))
	}
}

func TestCrossTenantIsolation(t *testing.T) {
	c := coord.New(coord.NewMemory())
	ok, err := c.TryDedicated("conn-x", "tenant-a")
	if err != nil || !ok {
		t.Fatal(err, ok)
	}
	ok, err = c.TryDedicated("conn-x", "tenant-b")
	if err != nil || ok {
		t.Fatalf("cross tenant occupy err=%v ok=%v", err, ok)
	}
}

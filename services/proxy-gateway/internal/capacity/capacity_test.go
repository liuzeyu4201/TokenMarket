package capacity

import (
	"os"
	"testing"
	"time"
)

func TestProfileMatchesContract(t *testing.T) {
	if TenantCount != 500 || SteadyRPS != 500 || BurstRPS != 1000 || StreamConns != 500 {
		t.Fatal("profile counts shrunk")
	}
	if SteadyDuration != 30*time.Minute || BurstDuration != 5*time.Minute {
		t.Fatal("duration shrunk")
	}
	if StreamDuration != 2*time.Hour || RecoverDuration != 10*time.Minute {
		t.Fatal("soak/recover shrunk")
	}
	if RPOLimit != 5*time.Minute || RTOLimit != 30*time.Minute {
		t.Fatal("rpo/rto shrunk")
	}
	s := Steady()
	if s.RPS != 500 || s.Tenants != 500 || s.Duration != 30*time.Minute {
		t.Fatalf("steady %+v", s)
	}
}

func TestDataset500UniqueIsolationKeys(t *testing.T) {
	ds := Dataset(DatasetSeed, TenantCount)
	if len(ds) != 500 {
		t.Fatalf("n=%d", len(ds))
	}
	seen := map[string]struct{}{}
	protos := map[string]int{}
	for _, tn := range ds {
		if _, ok := seen[tn.BuyerID]; ok {
			t.Fatalf("dup %s", tn.BuyerID)
		}
		seen[tn.BuyerID] = struct{}{}
		if tn.ProjectID == "" || tn.KeyID == "" || tn.BuyerID == tn.ProjectID {
			t.Fatal("tenant fields")
		}
		protos[tn.Protocol]++
	}
	if protos["openai"] == 0 || protos["anthropic"] == 0 || protos["vertex"] == 0 {
		t.Fatalf("protocols %+v", protos)
	}
}

func TestSteady500RPSGate(t *testing.T) {
	e := NewEngine()
	t.Cleanup(e.Close)
	rep := e.Run(Steady().WithDuration(time.Second))
	if !rep.PassSteady() {
		t.Fatalf("steady %+v", rep)
	}
	if rep.SuccessRate < SuccessFloor {
		t.Fatalf("success %f", rep.SuccessRate)
	}
	if rep.PlatformP95 > PlatformP95Max {
		t.Fatalf("p95 %s", rep.PlatformP95)
	}
	if rep.AchievedRPS < 0.9*float64(SteadyRPS) {
		t.Fatalf("rps %f", rep.AchievedRPS)
	}
}

func TestBurst1000AndRecover(t *testing.T) {
	e := NewEngine()
	t.Cleanup(e.Close)
	burst := e.Run(Burst().WithDuration(time.Second))
	if burst.Total == 0 {
		t.Fatal("no burst traffic")
	}
	if burst.OpenReservations != 0 || burst.DoubleCharge != 0 {
		t.Fatalf("ledger burst %+v", burst)
	}
	e.Mock.SetFail(true)
	_ = e.Run(Steady().WithDuration(200 * time.Millisecond))
	e.Mock.SetFail(false)
	rec := e.Run(Steady().WithDuration(time.Second))
	if !rec.PassSteady() {
		t.Fatalf("recover %+v", rec)
	}
}

func TestStream500DisconnectAndHeap(t *testing.T) {
	e := NewEngine()
	t.Cleanup(e.Close)
	rep := e.RunStream(StreamConns, 150*time.Millisecond)
	if rep.Total != 500 {
		t.Fatalf("conns %d", rep.Total)
	}
	if !rep.PassStream() {
		t.Fatalf("stream %+v", rep)
	}
}

func TestCapacityEngineTimeoutCoversStreamSoak(t *testing.T) {
	e := NewEngine()
	t.Cleanup(e.Close)
	if e.kernel.Limits.UpstreamTimeout < StreamDuration {
		t.Fatalf("upstream timeout %s < stream %s", e.kernel.Limits.UpstreamTimeout, StreamDuration)
	}
	// 6s > the previous 5s kernel deadline; 2 conns keep this off the 2h wall.
	rep := e.RunStream(2, 6*time.Second)
	if !rep.PassStream() {
		t.Fatalf("stream %+v", rep)
	}
}

func TestFaultNoDoubleCharge(t *testing.T) {
	e := NewEngine()
	t.Cleanup(e.Close)
	_ = e.Run(Steady().WithDuration(200 * time.Millisecond))
	e.Mock.SetFail(true)
	e.Mock.SetBacklog(5)
	_ = e.Run(Steady().WithDuration(200 * time.Millisecond))
	e.Mock.SetFail(false)
	e.Mock.SetBacklog(0)
	_ = e.Run(Steady().WithDuration(200 * time.Millisecond))
	if e.Ledger.DoubleCharge != 0 {
		t.Fatalf("double %d", e.Ledger.DoubleCharge)
	}
	if e.Ledger.Leaks != 0 {
		t.Fatalf("leaks %d", e.Ledger.Leaks)
	}
	if e.Ledger.OpenCount() != 0 {
		t.Fatalf("open %d", e.Ledger.OpenCount())
	}
}

func TestBackupRPORTO(t *testing.T) {
	led := NewMemLedger()
	_ = led.Reserve(nil, "r1", "p1", "k1", 1)
	led.Settle("r1")
	snap := led.Snapshot()
	snap.TakenAt = time.Now().Add(-4 * time.Minute)
	_ = led.Reserve(nil, "r2", "p2", "k2", 1)
	led.Settle("r2")
	start := time.Now()
	got := RestoreLedger(snap)
	rto := time.Since(start)
	rpo := time.Since(snap.TakenAt)
	if rpo > RPOLimit {
		t.Fatalf("rpo %s", rpo)
	}
	if rto > RTOLimit {
		t.Fatalf("rto %s", rto)
	}
	if _, ok := got.settled["r1"]; !ok {
		t.Fatal("missing restored r1")
	}
	if _, ok := got.settled["r2"]; ok {
		t.Fatal("post-backup r2 must not be in restored empty instance")
	}
}

func TestThreeConsecutivePasses(t *testing.T) {
	for i := 0; i < 3; i++ {
		e := NewEngine()
		rep := e.Run(Steady().WithDuration(time.Second))
		e.Close()
		if !rep.PassSteady() {
			t.Fatalf("run %d %+v", i+1, rep)
		}
	}
}

func TestFullProfiles(t *testing.T) {
	if os.Getenv("CAPACITY_FULL") != "1" {
		t.Skip("set CAPACITY_FULL=1 for 30m/5m/2h walls")
	}
	e := NewEngine()
	t.Cleanup(e.Close)
	steady := e.Run(Steady())
	if !steady.PassSteady() {
		t.Fatalf("full steady %+v", steady)
	}
	burst := e.Run(Burst())
	if !burst.PassSteady() {
		t.Fatalf("full burst %+v", burst)
	}
	stream := e.RunStream(StreamConns, StreamDuration)
	if !stream.PassStream() {
		t.Fatalf("full stream %+v", stream)
	}
}

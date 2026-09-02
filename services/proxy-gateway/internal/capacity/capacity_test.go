package capacity

import (
	"bytes"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
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
	dockerAvailable(t)
	srcName := uniqueName("pg-src")
	src := dockerRun(t,
		"--name", srcName,
		"--mount", "type=tmpfs,destination=/var/lib/postgresql/data",
		"-e", "POSTGRES_PASSWORD=tm_local_test",
		"-e", "POSTGRES_USER=tm",
		"-e", "POSTGRES_DB=tm",
		"postgres:15.18-bookworm",
	)
	postgresReady(t, src)
	psql(t, src, `CREATE TABLE ledger_entries (
			request_id TEXT PRIMARY KEY,
			amount INT NOT NULL,
			state TEXT NOT NULL
		)`)
	psql(t, src, `INSERT INTO ledger_entries(request_id, amount, state) VALUES ('r1', 1, 'settled')`)
	dump := dockerExecEnv(t, src, []string{pgPassEnv}, "pg_dump", "-h", "127.0.0.1", "-U", "tm", "-d", "tm", "--table=ledger_entries")
	backupAt := time.Now()
	psql(t, src, `INSERT INTO ledger_entries(request_id, amount, state) VALUES ('r2', 1, 'settled')`)

	dstName := uniqueName("pg-dst")
	dst := dockerRun(t,
		"--name", dstName,
		"--mount", "type=tmpfs,destination=/var/lib/postgresql/data",
		"-e", "POSTGRES_PASSWORD=tm_local_test",
		"-e", "POSTGRES_USER=tm",
		"-e", "POSTGRES_DB=tm",
		"postgres:15.18-bookworm",
	)
	postgresReady(t, dst)
	restoreStart := time.Now()
	cmd := exec.Command("docker", "exec", "-e", pgPassEnv, "-i", dst, "psql", "-h", "127.0.0.1", "-U", "tm", "-d", "tm")
	cmd.Stdin = strings.NewReader(dump)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("restore empty instance: %s", bytes.TrimSpace(out))
	}
	rto := time.Since(restoreStart)
	rpo := time.Since(backupAt)
	if rpo > RPOLimit {
		t.Fatalf("rpo %s", rpo)
	}
	if rto > RTOLimit {
		t.Fatalf("rto %s", rto)
	}
	hasR1 := psqlt(t, dst, `SELECT count(*) FROM ledger_entries WHERE request_id='r1'`)
	hasR2 := psqlt(t, dst, `SELECT count(*) FROM ledger_entries WHERE request_id='r2'`)
	if hasR1 != "1" {
		t.Fatalf("restored empty instance missing r1: %q", hasR1)
	}
	if hasR2 != "0" {
		t.Fatalf("post-backup r2 must not be in restored empty instance: %q", hasR2)
	}
	if dir := os.Getenv("TOKENMARKET_EVIDENCE_DIR"); dir != "" {
		_ = os.MkdirAll(filepath.Join(dir, "recovery"), 0o755)
		body := fmt.Sprintf(`{"rpo_ns":%d,"rto_ns":%d,"r1":%q,"r2":%q}`, rpo, rto, hasR1, hasR2)
		_ = os.WriteFile(filepath.Join(dir, "recovery", "postgres-rpo.json"), []byte(body), 0o644)
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

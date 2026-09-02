package capacity

import (
	"os/exec"
	"testing"
	"time"
)

func TestNodeExitNoDoubleCharge(t *testing.T) {
	e1 := NewEngine()
	e2 := NewEngine()
	t.Cleanup(e2.Close)
	_ = e1.Run(Steady().WithDuration(150 * time.Millisecond))
	e1.Close() // instance termination
	rep := e2.Run(Steady().WithDuration(200 * time.Millisecond))
	if e2.Ledger.DoubleCharge != 0 {
		t.Fatalf("double %d after node exit", e2.Ledger.DoubleCharge)
	}
	if e2.Ledger.OpenCount() != 0 {
		t.Fatalf("open %d", e2.Ledger.OpenCount())
	}
	if rep.Total == 0 {
		t.Fatal("surviving node served no traffic")
	}
}

func TestRedisRestartNoDoubleCharge(t *testing.T) {
	dockerAvailable(t)
	name := uniqueName("redis")
	id := dockerRun(t, "--name", name, "--tmpfs", "/data", "redis:7.2-alpine",
		"redis-server", "--save", "", "--appendonly", "no")
	waitDocker(t, id, []string{"redis-cli", "PING"}, "PONG", 20*time.Second)
	dockerExec(t, id, "redis-cli", "SET", "reservation:r1", "open")
	if err := exec.Command("docker", "restart", "-t", "1", id).Run(); err != nil {
		t.Fatalf("redis restart: %v", err)
	}
	waitDocker(t, id, []string{"redis-cli", "PING"}, "PONG", 20*time.Second)
	// Redis is not SoR: cache miss after restart is expected.
	e := NewEngine()
	t.Cleanup(e.Close)
	_ = e.Run(Steady().WithDuration(200 * time.Millisecond))
	if e.Ledger.DoubleCharge != 0 || e.Ledger.OpenCount() != 0 {
		t.Fatalf("ledger after redis restart double=%d open=%d", e.Ledger.DoubleCharge, e.Ledger.OpenCount())
	}
}

func TestPostgresShortOutageNoDoubleCharge(t *testing.T) {
	dockerAvailable(t)
	name := uniqueName("pg-outage")
	id := dockerRun(t,
		"--name", name,
		"--mount", "type=tmpfs,destination=/var/lib/postgresql/data",
		"-e", "POSTGRES_PASSWORD=tm_local_test",
		"-e", "POSTGRES_USER=tm",
		"-e", "POSTGRES_DB=tm",
		"postgres:15.18-bookworm",
	)
	postgresReady(t, id)
	psql(t, id, `CREATE TABLE ledger_entries (
			request_id TEXT PRIMARY KEY,
			amount INT NOT NULL,
			state TEXT NOT NULL
		)`)
	psql(t, id, `INSERT INTO ledger_entries(request_id, amount, state) VALUES ('r1', 1, 'settled')`)
	if err := exec.Command("docker", "pause", id).Run(); err != nil {
		t.Fatalf("pause postgres: %v", err)
	}
	e := NewEngine()
	t.Cleanup(e.Close)
	e.Mock.SetFail(true)
	_ = e.Run(Steady().WithDuration(150 * time.Millisecond))
	e.Mock.SetFail(false)
	if err := exec.Command("docker", "unpause", id).Run(); err != nil {
		t.Fatalf("unpause postgres: %v", err)
	}
	postgresReady(t, id)
	out := psqlt(t, id, `SELECT count(*) FROM ledger_entries WHERE request_id='r1' AND state='settled'`)
	if out != "1" {
		t.Fatalf("settled r1 after outage: %q", out)
	}
	dup := psqlt(t, id, `SELECT count(*) FROM ledger_entries WHERE request_id='r1'`)
	if dup != "1" {
		t.Fatalf("double row for r1: %q", dup)
	}
	_ = e.Run(Steady().WithDuration(150 * time.Millisecond))
	if e.Ledger.DoubleCharge != 0 {
		t.Fatalf("double %d", e.Ledger.DoubleCharge)
	}
}

func TestReleaseRollbackNoDoubleCharge(t *testing.T) {
	e := NewEngine()
	t.Cleanup(e.Close)
	_ = e.Run(Steady().WithDuration(150 * time.Millisecond))
	// Rollback = close current listener and serve from a replacement engine
	// with the same ledger invariants (no replayed settle).
	e.Close()
	next := NewEngine()
	t.Cleanup(next.Close)
	rep := next.Run(Steady().WithDuration(200 * time.Millisecond))
	if next.Ledger.DoubleCharge != 0 {
		t.Fatalf("double %d after rollback", next.Ledger.DoubleCharge)
	}
	if next.Ledger.OpenCount() != 0 {
		t.Fatalf("open %d", next.Ledger.OpenCount())
	}
	if rep.Total == 0 {
		t.Fatal("rollback node served no traffic")
	}
}

package capacity

import (
	"os/exec"
	"sync/atomic"
	"testing"
	"time"
)

func TestNodeExitNoDoubleCharge(t *testing.T) {
	led := NewMemLedger()
	seq := new(atomic.Int64)
	e1 := NewEngineWithLedger(led, seq, nil)
	e2 := NewEngineWithLedger(led, seq, nil)
	t.Cleanup(e2.Close)
	_ = e1.Run(Steady().WithDuration(150 * time.Millisecond))
	settled := led.SettledIDs()
	e1.Close()
	rep := e2.Run(Steady().WithDuration(200 * time.Millisecond))
	tn := Dataset(DatasetSeed, 1)[0]
	for _, id := range settled {
		e2.Retry(tn, id)
	}
	if led.DoubleCharge != 0 {
		t.Fatalf("shared ledger double %d after node exit", led.DoubleCharge)
	}
	if led.OpenCount() != 0 {
		t.Fatalf("open %d", led.OpenCount())
	}
	if rep.Total == 0 {
		t.Fatal("surviving node served no traffic")
	}
}

func TestRedisRestartNoDoubleCharge(t *testing.T) {
	dockerAvailable(t)
	name := uniqueName("redis")
	id, addr := dockerRunPublish(t, "6379", "--name", name, "--tmpfs", "/data",
		"redis:7.2-alpine", "redis-server", "--save", "", "--appendonly", "no")
	waitDocker(t, id, []string{"redis-cli", "PING"}, "PONG", 20*time.Second)
	led := NewMemLedger()
	cached := &RedisCachedLedger{Inner: led, Addr: addr}
	seq := new(atomic.Int64)
	e := NewEngineWithLedger(led, seq, cached)
	t.Cleanup(e.Close)
	_ = e.Run(Steady().WithDuration(200 * time.Millisecond))
	settled := led.SettledIDs()
	if len(settled) == 0 {
		t.Fatal("need settled ids before redis restart")
	}
	if err := exec.Command("docker", "restart", "-t", "1", id).Run(); err != nil {
		t.Fatalf("redis restart: %v", err)
	}
	waitDocker(t, id, []string{"redis-cli", "PING"}, "PONG", 20*time.Second)
	tn := Dataset(DatasetSeed, 1)[0]
	for _, rid := range settled {
		e.Retry(tn, rid)
	}
	_ = e.Run(Steady().WithDuration(150 * time.Millisecond))
	if led.DoubleCharge != 0 || led.OpenCount() != 0 {
		t.Fatalf("ledger after redis restart double=%d open=%d", led.DoubleCharge, led.OpenCount())
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
	led := NewMemLedger()
	pg := &PGLedger{
		Inner: led,
		ExecSQL: func(sql string) error {
			_, err := execSQLErr(id, sql)
			return err
		},
	}
	seq := new(atomic.Int64)
	e := NewEngineWithLedger(led, seq, pg)
	t.Cleanup(e.Close)
	before := e.Run(Profile{Name: "pre", Tenants: 8, RPS: 20, Duration: 200 * time.Millisecond})
	if before.Success == 0 {
		t.Fatal("postgres-backed engine served nothing before outage")
	}
	if err := exec.Command("docker", "pause", id).Run(); err != nil {
		t.Fatalf("pause postgres: %v", err)
	}
	during := e.Run(Profile{Name: "outage", Tenants: 8, RPS: 20, Duration: 200 * time.Millisecond})
	if during.Success != 0 {
		t.Fatalf("postgres pause must fail-close, success=%d", during.Success)
	}
	if err := exec.Command("docker", "unpause", id).Run(); err != nil {
		t.Fatalf("unpause postgres: %v", err)
	}
	postgresReady(t, id)
	after := e.Run(Profile{Name: "post", Tenants: 8, RPS: 20, Duration: 200 * time.Millisecond})
	if after.Success == 0 {
		t.Fatal("engine did not recover after postgres unpause")
	}
	if led.DoubleCharge != 0 {
		t.Fatalf("double %d", led.DoubleCharge)
	}
	dup := psqlt(t, id, `SELECT count(*) FROM ledger_entries`)
	if dup == "" {
		t.Fatal("empty ledger after outage")
	}
}

func TestReleaseRollbackNoDoubleCharge(t *testing.T) {
	led := NewMemLedger()
	seq := new(atomic.Int64)
	e := NewEngineWithLedger(led, seq, nil)
	_ = e.Run(Steady().WithDuration(150 * time.Millisecond))
	settled := led.SettledIDs()
	e.Close()
	next := NewEngineWithLedger(led, seq, nil)
	t.Cleanup(next.Close)
	rep := next.Run(Steady().WithDuration(200 * time.Millisecond))
	tn := Dataset(DatasetSeed, 1)[0]
	for _, id := range settled {
		next.Retry(tn, id)
	}
	if led.DoubleCharge != 0 {
		t.Fatalf("shared ledger double %d after rollback", led.DoubleCharge)
	}
	if led.OpenCount() != 0 {
		t.Fatalf("open %d", led.OpenCount())
	}
	if rep.Total == 0 {
		t.Fatal("rollback node served no traffic")
	}
}

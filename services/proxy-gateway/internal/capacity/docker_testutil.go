package capacity

import (
	"bytes"
	"fmt"
	"os/exec"
	"strings"
	"testing"
	"time"
)

func dockerAvailable(t *testing.T) {
	t.Helper()
	if _, err := exec.LookPath("docker"); err != nil {
		t.Skip("docker CLI not installed")
	}
	out, err := exec.Command("docker", "info").CombinedOutput()
	if err != nil {
		t.Fatalf("docker daemon not usable: %s", bytes.TrimSpace(out))
	}
}

func dockerRun(t *testing.T, args ...string) string {
	t.Helper()
	cmd := exec.Command("docker", append([]string{"run", "-d", "--pull", "never"}, args...)...)
	out, err := cmd.CombinedOutput()
	id := strings.TrimSpace(string(out))
	if err != nil {
		t.Fatalf("docker run: %s", bytes.TrimSpace(out))
	}
	t.Cleanup(func() {
		_ = exec.Command("docker", "rm", "-f", id).Run()
	})
	return id
}

func dockerExec(t *testing.T, id string, args ...string) string {
	t.Helper()
	return dockerExecEnv(t, id, nil, args...)
}

func dockerExecEnv(t *testing.T, id string, env []string, args ...string) string {
	t.Helper()
	argv := []string{"exec"}
	for _, e := range env {
		argv = append(argv, "-e", e)
	}
	argv = append(argv, id)
	argv = append(argv, args...)
	cmd := exec.Command("docker", argv...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("docker exec %v: %s", args, bytes.TrimSpace(out))
	}
	return string(out)
}

const pgPassEnv = "PGPASSWORD=tm_local_test"

func waitDocker(t *testing.T, id string, args []string, want string, d time.Duration) {
	t.Helper()
	deadline := time.Now().Add(d)
	var last string
	for time.Now().Before(deadline) {
		cmd := exec.Command("docker", append([]string{"exec", id}, args...)...)
		out, err := cmd.CombinedOutput()
		last = string(out)
		if err == nil && (want == "" || strings.Contains(last, want)) {
			return
		}
		time.Sleep(250 * time.Millisecond)
	}
	t.Fatalf("timeout waiting for %v: %s", args, last)
}

func postgresReady(t *testing.T, id string) {
	t.Helper()
	deadline := time.Now().Add(45 * time.Second)
	var last string
	for time.Now().Before(deadline) {
		cmd := exec.Command("docker", "exec", "-e", pgPassEnv, id, "pg_isready", "-h", "127.0.0.1", "-U", "tm", "-d", "tm")
		out, err := cmd.CombinedOutput()
		last = string(out)
		if err == nil && strings.Contains(last, "accepting connections") {
			cmd = exec.Command("docker", "exec", "-e", pgPassEnv, id, "psql", "-h", "127.0.0.1", "-U", "tm", "-d", "tm", "-tAc", "SELECT 1")
			out, err = cmd.CombinedOutput()
			last = string(out)
			if err == nil && strings.Contains(last, "1") {
				return
			}
		}
		time.Sleep(300 * time.Millisecond)
	}
	t.Fatalf("postgres not ready: %s", last)
}

func psql(t *testing.T, id, sql string) string {
	t.Helper()
	return dockerExecEnv(t, id, []string{pgPassEnv}, "psql", "-h", "127.0.0.1", "-U", "tm", "-d", "tm", "-v", "ON_ERROR_STOP=1", "-c", sql)
}

func psqlt(t *testing.T, id, sql string) string {
	t.Helper()
	return strings.TrimSpace(dockerExecEnv(t, id, []string{pgPassEnv}, "psql", "-h", "127.0.0.1", "-U", "tm", "-d", "tm", "-tAc", sql))
}

func uniqueName(prefix string) string {
	return fmt.Sprintf("tm-%s-%d", prefix, time.Now().UnixNano())
}

package endpcatalog_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

func TestMustLoadFromEnvMismatch(t *testing.T) {
	t.Setenv("TOKENMARKET_CATALOG_MAJOR", "9")
	_, err := endpcatalog.MustLoadFromEnv()
	if err == nil {
		t.Fatal("expected mismatch")
	}
	le, ok := err.(*endpcatalog.LoadError)
	if !ok || le.Code != endpcatalog.CodeVersionMismatch {
		t.Fatalf("got %v", err)
	}
}

func TestMustLoadFromEnvFileOverride(t *testing.T) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	path := filepath.Join(dir, "catalog.json")
	raw, err := os.ReadFile("catalog.snapshot.json")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("TOKENMARKET_ENDPOINT_CATALOG", path)
	t.Setenv("TOKENMARKET_CATALOG_MAJOR", "1")
	got, err := endpcatalog.MustLoadFromEnv()
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Records) != len(c.Records) {
		t.Fatalf("records %d != %d", len(got.Records), len(c.Records))
	}
}

package chatcompat_test

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestContractAssetsPresentAndOpenAPIParseable(t *testing.T) {
	root := repoRoot(t)
	dir := filepath.Join(root, "shared", "contracts", "volcano-openai-compat", "v1")
	files := []string{
		"volcano-openai-compat.openapi.yaml",
		"error-classification.md",
		"request-field-allowlist.md",
		"header-allowlist.md",
		"sse-events.md",
		"usage-observation.md",
		"upstream-volcano-chat.md",
		"consumer-notes.md",
	}
	for _, f := range files {
		p := filepath.Join(dir, f)
		if _, err := os.Stat(p); err != nil {
			t.Fatalf("missing %s: %v", p, err)
		}
	}
	raw, err := os.ReadFile(filepath.Join(dir, "volcano-openai-compat.openapi.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err := yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatalf("openapi yaml: %v", err)
	}
	if doc["openapi"] == nil {
		t.Fatal("missing openapi version")
	}
}

func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("caller")
	}
	dir := filepath.Dir(file)
	for i := 0; i < 8; i++ {
		if _, err := os.Stat(filepath.Join(dir, "shared", "contracts")); err == nil {
			return dir
		}
		dir = filepath.Dir(dir)
	}
	t.Fatal("repo root not found")
	return ""
}

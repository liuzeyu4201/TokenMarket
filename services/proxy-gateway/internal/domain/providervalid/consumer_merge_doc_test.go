package providervalid_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestConsumerMergeRulesDocument(t *testing.T) {
	root := repoRoot(t)
	p := filepath.Join(root, "shared", "contracts", "volcano-key-validation", "v1", "consumer-merge-rules.md")
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	s := string(b)
	for _, needle := range []string{"MUST NOT", "invalid", "rate_limited", "quota_unavailable"} {
		if !strings.Contains(s, needle) {
			t.Fatalf("missing %q in merge rules", needle)
		}
	}
}

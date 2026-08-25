package chatcompat_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestConsumerNotesForbidPermanentInvalidOnTransient(t *testing.T) {
	p := filepath.Join(repoRoot(t), "shared", "contracts", "volcano-openai-compat", "v1", "consumer-notes.md")
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	s := string(b)
	for _, needle := range []string{"truncated_stream", "不得", "invalid"} {
		if !strings.Contains(s, needle) {
			t.Fatalf("missing %q", needle)
		}
	}
	if !strings.Contains(s, "rate_limited") || !strings.Contains(s, "permanent") && !strings.Contains(s, "永久") {
		t.Fatal("must declare transient must not overwrite permanent invalid")
	}
}

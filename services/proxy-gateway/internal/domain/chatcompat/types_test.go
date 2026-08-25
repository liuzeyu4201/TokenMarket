package chatcompat_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestErrorCategoryEnumMatchesContract(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join(repoRoot(t), "shared", "contracts", "volcano-openai-compat", "v1", "error-classification.md"))
	if err != nil {
		t.Fatal(err)
	}
	text := string(raw)
	for _, cat := range chatcompat.AllErrorCategories() {
		needle := "`" + string(cat) + "`"
		if !strings.Contains(text, needle) {
			t.Errorf("contract missing %s", cat)
		}
	}
	required := []string{
		"unsupported_parameter", "unsupported_endpoint", "truncated_stream",
		"success", "invalid", "forbidden", "rate_limited",
	}
	got := map[string]bool{}
	for _, c := range chatcompat.AllErrorCategories() {
		got[string(c)] = true
	}
	for _, r := range required {
		if !got[r] {
			t.Errorf("enum missing %s", r)
		}
	}
}

func TestStreamKinds(t *testing.T) {
	for _, k := range []chatcompat.StreamKind{
		chatcompat.KindDelta, chatcompat.KindDone, chatcompat.KindTruncated, chatcompat.KindError,
	} {
		if k == "" {
			t.Fatal("empty kind")
		}
	}
}

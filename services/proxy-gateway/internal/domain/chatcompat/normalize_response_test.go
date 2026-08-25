package chatcompat_test

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestNormalizeSuccessAndMissingUsage(t *testing.T) {
	ok := []byte(`{"id":"chatcmpl-1","object":"chat.completion","created":1,"model":"ep-x","choices":[{"index":0,"message":{"role":"assistant","content":"hi"},"finish_reason":"stop"}]}`)
	r := chatcompat.NormalizeNonStream(ok, "doubao-pro-32k")
	if r.ErrorCategory != chatcompat.CategorySuccess {
		t.Fatalf("cat %s", r.ErrorCategory)
	}
	if r.UsageStatus != chatcompat.UsageMissing {
		t.Fatalf("usage %s", r.UsageStatus)
	}
	if r.Usage != nil {
		t.Fatal("missing usage object")
	}
	if r.Model != "doubao-pro-32k" {
		t.Fatalf("public model %s", r.Model)
	}
	if len(r.Choices) != 1 {
		t.Fatal("choices")
	}
}

func TestNormalizeNoChoicesInvalidResponse(t *testing.T) {
	r := chatcompat.NormalizeNonStream([]byte(`{"id":"x","choices":[]}`), "doubao-pro-32k")
	if r.ErrorCategory != chatcompat.CategoryInvalidResponse {
		t.Fatalf("%s", r.ErrorCategory)
	}
}

func TestNormalizeInconsistentUsageKeepsSuccess(t *testing.T) {
	body := []byte(`{"id":"1","choices":[{"index":0,"message":{"role":"assistant","content":"a"},"finish_reason":"stop"}],"usage":{"prompt_tokens":8,"completion_tokens":2,"total_tokens":1}}`)
	r := chatcompat.NormalizeNonStream(body, "doubao-pro-32k")
	if r.ErrorCategory != chatcompat.CategorySuccess {
		t.Fatalf("%s", r.ErrorCategory)
	}
	if r.UsageStatus != chatcompat.UsageInconsistent {
		t.Fatalf("%s", r.UsageStatus)
	}
	if r.Usage == nil || *r.Usage.TotalTokens != 1 {
		t.Fatalf("rewritten %#v", r.Usage)
	}
}

func TestFixtureMalformed(t *testing.T) {
	p := filepath.Join(repoRoot(t), "services", "proxy-gateway", "internal", "infrastructure", "platform", "volcano", "fixtures", "chat_malformed.json")
	b, err := os.ReadFile(p)
	if err != nil {
		t.Skip("fixture later")
		return
	}
	r := chatcompat.NormalizeNonStream(b, "doubao-pro-32k")
	if r.ErrorCategory != chatcompat.CategoryInvalidResponse {
		t.Fatalf("%s", r.ErrorCategory)
	}
}

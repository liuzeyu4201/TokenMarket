package chatcompat_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestUsageComplete(t *testing.T) {
	p, c, tot := 8, 2, 10
	st, u := chatcompat.InspectUsage(&p, &c, &tot, true)
	if st != chatcompat.UsageComplete || u == nil || u.Source != "upstream" {
		t.Fatalf("%s %#v", st, u)
	}
}

func TestUsageMissingNoFakeZero(t *testing.T) {
	st, u := chatcompat.InspectUsage(nil, nil, nil, false)
	if st != chatcompat.UsageMissing {
		t.Fatalf("status %s", st)
	}
	if u != nil {
		t.Fatal("missing must not emit usage object")
	}
	zero := 0
	fake := &chatcompat.Usage{PromptTokens: &zero, CompletionTokens: &zero, TotalTokens: &zero}
	if !chatcompat.ZeroFilledUsage(fake, chatcompat.UsageMissing) {
		t.Fatal("should detect fake zeros")
	}
}

func TestUsageInconsistentDoesNotRewrite(t *testing.T) {
	p, c, tot := 8, 2, 5
	st, u := chatcompat.InspectUsage(&p, &c, &tot, true)
	if st != chatcompat.UsageInconsistent {
		t.Fatalf("status %s", st)
	}
	if u == nil || *u.TotalTokens != 5 || *u.PromptTokens != 8 {
		t.Fatalf("rewrote %#v", u)
	}
}

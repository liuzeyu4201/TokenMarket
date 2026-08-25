package chatcompat_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestModelMapIdentityAndOverride(t *testing.T) {
	m := chatcompat.ModelMap{Allowlist: []string{"doubao-pro-32k", "doubao-lite-32k"}}
	up, cat := m.ResolveOutbound("doubao-pro-32k")
	if cat != "" || up != "doubao-pro-32k" {
		t.Fatalf("identity %s %s", up, cat)
	}
	m.PublicToUpstream = map[string]string{"doubao-pro-32k": "ep-2024-internal"}
	up, cat = m.ResolveOutbound("doubao-pro-32k")
	if cat != "" || up != "ep-2024-internal" {
		t.Fatalf("override %s %s", up, cat)
	}
	if got := m.PublicFromUpstream("ep-2024-internal", "doubao-pro-32k"); got != "doubao-pro-32k" {
		t.Fatalf("rewrite %s", got)
	}
}

func TestUnknownPublicModelRejected(t *testing.T) {
	m := chatcompat.ModelMap{Allowlist: []string{"doubao-pro-32k"}}
	_, cat := m.ResolveOutbound("gpt-4")
	if cat != chatcompat.CategoryUnsupportedParameter {
		t.Fatalf("got %s", cat)
	}
}

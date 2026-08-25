package chatcompat_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestConfigValidateEmptyAllowlist(t *testing.T) {
	cfg := chatcompat.Config{Allowlist: nil, DefaultDeadlineSec: 60, MaxBodyBytes: 10}
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected fail-closed")
	}
}

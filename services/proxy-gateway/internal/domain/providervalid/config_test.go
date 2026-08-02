package providervalid_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestConfigC1FailClosed(t *testing.T) {
	cfg := providervalid.Config{
		AppEnv:             "prod",
		Allowlist:          []string{"m1"},
		DefaultRetryAfter:  5,
		MaxRetryAfter:      300,
		GlobalConcurrency:  32,
		PerCredConcurrency: 1,
		InternalEnabled:    true,
		InternalToken:      "tok",
		InternalBind:       "0.0.0.0",
		AllowNonLoopback:   false,
	}
	if err := cfg.Validate(); err == nil {
		t.Fatal("expected C1 fail")
	}
	cfg.InternalBind = "127.0.0.1"
	if err := cfg.Validate(); err != nil {
		t.Fatalf("loopback should pass: %v", err)
	}
	cfg.InternalBind = "0.0.0.0"
	cfg.AllowNonLoopback = true
	if err := cfg.Validate(); err != nil {
		t.Fatalf("allow non-loopback: %v", err)
	}
	cfg.AppEnv = "local"
	cfg.AllowNonLoopback = false
	cfg.InternalBind = "0.0.0.0"
	if err := cfg.Validate(); err != nil {
		t.Fatalf("local allows: %v", err)
	}
}

func TestConfigEmptyAllowlist(t *testing.T) {
	cfg := providervalid.Config{
		AppEnv: "local", Allowlist: nil,
		DefaultRetryAfter: 5, MaxRetryAfter: 300,
		GlobalConcurrency: 1, PerCredConcurrency: 1,
	}
	if err := cfg.Validate(); err == nil {
		t.Fatal("empty allowlist")
	}
}

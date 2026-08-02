package providervalid_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestLoadConfigFromEnvDefaults(t *testing.T) {
	t.Setenv("APP_ENV", "local")
	t.Setenv("PROVIDER_VALIDATE_INTERNAL_ENABLED", "false")
	t.Setenv("VOLCANO_V01_CHAT_MODELS", "m1,m2")
	t.Setenv("VOLCANO_VALIDATE_GLOBAL_CONCURRENCY", "16")
	t.Setenv("VOLCANO_VALIDATE_DEFAULT_RETRY_AFTER_SECONDS", "7")
	t.Setenv("VOLCANO_VALIDATE_MAX_RETRY_AFTER_SECONDS", "100")
	t.Setenv("PROVIDER_VALIDATE_INTERNAL_TOKEN", "")
	cfg, err := providervalid.LoadConfigFromEnv()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.GlobalConcurrency != 16 || cfg.DefaultRetryAfter != 7 {
		t.Fatalf("%+v", cfg)
	}
	if len(cfg.Allowlist) != 2 {
		t.Fatalf("allowlist %v", cfg.Allowlist)
	}
}

func TestLoadConfigInternalRequiresToken(t *testing.T) {
	t.Setenv("APP_ENV", "local")
	t.Setenv("PROVIDER_VALIDATE_INTERNAL_ENABLED", "true")
	t.Setenv("PROVIDER_VALIDATE_INTERNAL_TOKEN", "")
	t.Setenv("VOLCANO_V01_CHAT_MODELS", "m1")
	_, err := providervalid.LoadConfigFromEnv()
	if err == nil {
		t.Fatal("expected token required")
	}
}

func TestSuggestedActions(t *testing.T) {
	cases := map[providervalid.ErrorCategory]providervalid.SuggestedAction{
		providervalid.CategoryInvalid:             providervalid.ActionFixCredential,
		providervalid.CategoryZeroQuota:           providervalid.ActionAddQuota,
		providervalid.CategoryNoSupportedModels:   providervalid.ActionEnableModels,
		providervalid.CategoryRateLimited:         providervalid.ActionRetryLater,
		providervalid.CategoryUnsupportedPlatform: providervalid.ActionUnsupported,
		providervalid.CategorySuccess:             providervalid.ActionNone,
		providervalid.CategoryInvalidResponse:     providervalid.ActionRetryLater,
	}
	for cat, want := range cases {
		if got := providervalid.SuggestedActionFor(cat); got != want {
			t.Fatalf("%s -> %s want %s", cat, got, want)
		}
	}
}

func TestClassifyHTTPOther4xx(t *testing.T) {
	if providervalid.ClassifyHTTPStatus(400) != providervalid.CategoryInvalidResponse {
		t.Fatal("400")
	}
}

func TestAssertQuotaInvariantFalseWhenZeroString(t *testing.T) {
	// 直接构造绕过 NewResult 的坏结果
	z := "0"
	r := providervalid.CredentialValidationResult{
		ErrorCategory:  providervalid.CategoryQuotaUnavailable,
		RemainingQuota: &z,
	}
	if providervalid.AssertQuotaUnavailableInvariant(r) {
		t.Fatal("should fail invariant")
	}
}

func TestContainsSecretShort(t *testing.T) {
	if providervalid.ContainsSecret("ab", "ab") {
		t.Fatal("short secrets ignored")
	}
	if providervalid.RedactString("hello", "missing") != "hello" {
		t.Fatal("no-op redact")
	}
}

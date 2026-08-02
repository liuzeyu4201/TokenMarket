package application_test

import (
	"context"
	"sync/atomic"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/concurrency"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

type stubModels struct {
	res volcano.ModelsResult
}

func (s stubModels) ListModels(ctx context.Context, apiKey string) volcano.ModelsResult {
	_ = ctx
	_ = apiKey
	return s.res
}

func testCfg() providervalid.Config {
	return providervalid.Config{
		AppEnv:             "local",
		BaseURL:            "http://example.invalid",
		Allowlist:          []string{"doubao-pro-32k", "doubao-lite-32k"},
		DefaultRetryAfter:  5,
		MaxRetryAfter:      300,
		GateHMACSecret:     "test-secret",
		GlobalConcurrency:  32,
		PerCredConcurrency: 1,
	}
}

func TestValidateUnsupportedPlatform(t *testing.T) {
	v := &application.Validator{
		Cfg:    testCfg(),
		Models: stubModels{},
		Quota:  volcano.NoopQuotaReader{},
		Gate:   concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:    time.Now,
	}
	r := v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "openai", APIKey: "sk-synthetic-test-key-not-real",
	})
	if r.ErrorCategory != providervalid.CategoryUnsupportedPlatform {
		t.Fatalf("%+v", r)
	}
}

func TestValidateNoopQuotaUnavailable(t *testing.T) {
	v := &application.Validator{
		Cfg: testCfg(),
		Models: stubModels{res: volcano.ModelsResult{
			AuthOK: true, ModelIDs: []string{"doubao-pro-32k"},
		}},
		Quota: volcano.NoopQuotaReader{},
		Gate:  concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:   time.Now,
	}
	r := v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real",
	})
	if r.ErrorCategory != providervalid.CategoryQuotaUnavailable {
		t.Fatalf("%+v", r)
	}
	if r.RemainingQuota != nil {
		t.Fatalf("quota must be null, got %v", r.RemainingQuota)
	}
	if r.Validity != providervalid.ValidityValid {
		t.Fatalf("validity %s", r.Validity)
	}
}

func TestValidateSuccessWithStubQuota(t *testing.T) {
	v := &application.Validator{
		Cfg: testCfg(),
		Models: stubModels{res: volcano.ModelsResult{
			AuthOK: true, ModelIDs: []string{"doubao-pro-32k", "other"},
		}},
		Quota: volcano.NewPositiveStub("42", "CNY_fen"),
		Gate:  concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:   time.Now,
	}
	r := v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real",
	})
	if r.ErrorCategory != providervalid.CategorySuccess {
		t.Fatalf("%+v", r)
	}
	if r.RemainingQuota == nil || *r.RemainingQuota != "42" {
		t.Fatalf("quota %+v", r.RemainingQuota)
	}
	if len(r.SupportedModels) != 1 || r.SupportedModels[0] != "doubao-pro-32k" {
		t.Fatalf("models %v", r.SupportedModels)
	}
}

func TestValidateZeroQuota(t *testing.T) {
	v := &application.Validator{
		Cfg: testCfg(),
		Models: stubModels{res: volcano.ModelsResult{
			AuthOK: true, ModelIDs: []string{"doubao-pro-32k"},
		}},
		Quota: volcano.NewZeroStub("CNY_fen"),
		Gate:  concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:   time.Now,
	}
	r := v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: "sk-synthetic",
	})
	if r.ErrorCategory != providervalid.CategoryZeroQuota {
		t.Fatalf("%+v", r)
	}
}

func TestValidateNoSupportedModels(t *testing.T) {
	v := &application.Validator{
		Cfg: testCfg(),
		Models: stubModels{res: volcano.ModelsResult{
			AuthOK: true, ModelIDs: []string{"not-in-allowlist"},
		}},
		Quota: volcano.NewPositiveStub("10", "CNY_fen"),
		Gate:  concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:   time.Now,
	}
	r := v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: "sk-synthetic",
	})
	if r.ErrorCategory != providervalid.CategoryNoSupportedModels {
		t.Fatalf("%+v", r)
	}
	if r.Validity != providervalid.ValidityValid {
		t.Fatal("must remain valid")
	}
}

func TestValidateInvalidKeyNoLeak(t *testing.T) {
	key := "sk-super-secret-should-not-appear"
	v := &application.Validator{
		Cfg: testCfg(),
		Models: stubModels{res: volcano.ModelsResult{
			Category: providervalid.CategoryInvalid,
		}},
		Quota: volcano.NoopQuotaReader{},
		Gate:  concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:   time.Now,
	}
	r := v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: key,
	})
	if r.ErrorCategory != providervalid.CategoryInvalid {
		t.Fatalf("%+v", r)
	}
	// Result JSON-ish fields should not embed key
	if providervalid.ContainsSecret(r.CredentialRef, key) {
		t.Fatal("ref leak")
	}
	if r.SuggestedAction != providervalid.ActionFixCredential {
		t.Fatalf("action %s", r.SuggestedAction)
	}
}

// TestValidateSC002aDefault32AndPerCred 验收 SC-002a：默认 32 全局与单 Key 串行。
func TestValidateSC002aDefault32AndPerCred(t *testing.T) {
	var calls atomic.Int32
	cfg := testCfg()
	cfg.GlobalConcurrency = 32
	cfg.PerCredConcurrency = 1
	v := &application.Validator{
		Cfg:    cfg,
		Models: countingModels{n: &calls, res: volcano.ModelsResult{AuthOK: true, ModelIDs: []string{"doubao-pro-32k"}}},
		Quota:  volcano.NoopQuotaReader{},
		Gate:   concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:    time.Now,
	}
	// fill 32 unique keys
	releases := make([]func(), 0, 32)
	for i := 0; i < 32; i++ {
		rel, ok := v.Gate.Acquire("fill-" + string(rune('A'+i%26)) + string(rune('0'+i/26)) + string(rune('a'+i%10)))
		// use deterministic unique keys
		_ = rel
		_ = ok
	}
	// rebuild with clean gate and proper unique keys
	v.Gate = concurrency.NewValidateGate(32, 1, "test-secret")
	releases = releases[:0]
	for i := 0; i < 32; i++ {
		key := "fill-key-" + itoaApp(i)
		rel, ok := v.Gate.Acquire(key)
		if !ok {
			t.Fatalf("fill %d", i)
		}
		releases = append(releases, rel)
	}
	calls.Store(0)
	r := v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: "sk-33rd", RequestID: "sc002a",
	})
	if r.ErrorCategory != providervalid.CategoryTemporaryUnavailable {
		t.Fatalf("33rd want temporary, got %s", r.ErrorCategory)
	}
	if calls.Load() != 0 {
		t.Fatalf("models must not run on gate reject, calls=%d", calls.Load())
	}
	for _, rel := range releases {
		rel()
	}

	// per-cred: hold same key
	rel, ok := v.Gate.Acquire("sk-same")
	if !ok {
		t.Fatal("hold")
	}
	defer rel()
	calls.Store(0)
	r2 := v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: "sk-same",
	})
	if r2.ErrorCategory != providervalid.CategoryTemporaryUnavailable {
		t.Fatalf("same key 2nd: %s", r2.ErrorCategory)
	}
	if calls.Load() != 0 {
		t.Fatal("models called on per-cred reject")
	}
}

func itoaApp(n int) string {
	if n == 0 {
		return "0"
	}
	var b [12]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	return string(b[i:])
}

func TestValidateGateRejectsNoModelsCall(t *testing.T) {
	var calls atomic.Int32
	v := &application.Validator{
		Cfg:    testCfg(),
		Models: countingModels{n: &calls, res: volcano.ModelsResult{AuthOK: true, ModelIDs: []string{"doubao-pro-32k"}}},
		Quota:  volcano.NoopQuotaReader{},
		Gate:   concurrency.NewValidateGate(1, 1, "test-secret"),
		Now:    time.Now,
	}
	// occupy global
	rel, ok := v.Gate.Acquire("other")
	if !ok {
		t.Fatal("setup")
	}
	defer rel()
	r := v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: "sk-blocked",
	})
	if r.ErrorCategory != providervalid.CategoryTemporaryUnavailable {
		t.Fatalf("%+v", r)
	}
	if calls.Load() != 0 {
		t.Fatalf("models called %d", calls.Load())
	}
}

type countingModels struct {
	n   *atomic.Int32
	res volcano.ModelsResult
}

func (c countingModels) ListModels(ctx context.Context, apiKey string) volcano.ModelsResult {
	c.n.Add(1)
	return c.res
}

func TestValidateCancelPathNoKeyInRef(t *testing.T) {
	key := "sk-cancel-path-key"
	v := &application.Validator{
		Cfg: testCfg(),
		Models: stubModels{res: volcano.ModelsResult{
			Category: providervalid.CategoryTimeout,
		}},
		Quota: volcano.NoopQuotaReader{},
		Gate:  concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:   time.Now,
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	r := v.ValidateCredential(ctx, providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: key,
	})
	if providervalid.ContainsSecret(r.CredentialRef, key) {
		t.Fatal("leak")
	}
}

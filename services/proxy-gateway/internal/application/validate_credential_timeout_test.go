package application_test

import (
	"context"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/concurrency"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

type slowModels struct{}

func (slowModels) ListModels(ctx context.Context, apiKey string) volcano.ModelsResult {
	select {
	case <-ctx.Done():
		return volcano.ModelsResult{Category: providervalid.ClassifyTransportError(ctx.Err())}
	case <-time.After(5 * time.Second):
		return volcano.ModelsResult{AuthOK: true}
	}
}

func TestValidateHonorsShortDeadline(t *testing.T) {
	v := &application.Validator{
		Cfg:    testCfg(),
		Models: slowModels{},
		Quota:  volcano.NoopQuotaReader{},
		Gate:   concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:    time.Now,
	}
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	start := time.Now()
	r := v.ValidateCredential(ctx, providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: "sk-synthetic",
	})
	if time.Since(start) > 2*time.Second {
		t.Fatal("took too long")
	}
	if r.ErrorCategory != providervalid.CategoryTimeout &&
		r.ErrorCategory != providervalid.CategoryTemporaryUnavailable {
		t.Fatalf("cat %s", r.ErrorCategory)
	}
}

package providervalid_test

import (
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestQuotaUnavailableNoZero(t *testing.T) {
	zero := "0"
	r := providervalid.NewResult("volcano", providervalid.CategoryQuotaUnavailable,
		providervalid.ValidityValid, providervalid.AvailabilityUnavailable,
		nil, &zero, nil, nil, "ref", time.Now())
	if r.RemainingQuota != nil {
		t.Fatalf("remaining must be nil, got %v", r.RemainingQuota)
	}
	if !providervalid.AssertQuotaUnavailableInvariant(r) {
		t.Fatal("invariant")
	}
}

func TestRateLimitedRequiresRetry(t *testing.T) {
	r := providervalid.NewResult("volcano", providervalid.CategoryRateLimited,
		providervalid.ValidityUnknown, providervalid.AvailabilityUnavailable,
		nil, nil, nil, nil, "ref", time.Now())
	if r.RetryAfterSeconds == nil || *r.RetryAfterSeconds < 1 {
		t.Fatal("retry required")
	}
}

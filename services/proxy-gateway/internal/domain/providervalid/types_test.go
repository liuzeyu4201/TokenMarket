package providervalid_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestAllErrorCategoriesMatchContract(t *testing.T) {
	want := map[providervalid.ErrorCategory]bool{
		"success": true, "invalid": true, "forbidden": true, "zero_quota": true,
		"quota_unavailable": true, "no_supported_models": true, "rate_limited": true,
		"temporary_unavailable": true, "timeout": true, "invalid_response": true,
		"unsupported_platform": true,
	}
	got := providervalid.AllErrorCategories()
	if len(got) != len(want) {
		t.Fatalf("len=%d want %d", len(got), len(want))
	}
	for _, c := range got {
		if !want[c] {
			t.Fatalf("unexpected category %q", c)
		}
	}
}

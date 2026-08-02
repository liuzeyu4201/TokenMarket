package providervalid_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestRetryAfterDefaultsAndClamp(t *testing.T) {
	if providervalid.ParseRetryAfter("", 5, 300) != 5 {
		t.Fatal("default 5")
	}
	if providervalid.ParseRetryAfter("1", 5, 300) != 1 {
		t.Fatal("min")
	}
	if providervalid.ParseRetryAfter("301", 5, 300) != 300 {
		t.Fatal("max")
	}
}

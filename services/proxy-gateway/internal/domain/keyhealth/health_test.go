package keyhealth_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keyhealth"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestMapValidateCategory(t *testing.T) {
	h, pause := keyhealth.MapValidateCategory(providervalid.CategoryInvalid)
	if h != "invalid" || !pause {
		t.Fatal(h, pause)
	}
	h, pause = keyhealth.MapValidateCategory(providervalid.CategorySuccess)
	if h != "healthy" || pause {
		t.Fatal(h, pause)
	}
	h, _ = keyhealth.MapValidateCategory(providervalid.CategoryQuotaUnavailable)
	if h != "unknown" {
		t.Fatal(h)
	}
}

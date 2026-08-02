package providervalid_test

import (
	"fmt"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestErrorPathNoKeyLeak(t *testing.T) {
	key := "sk-very-secret-provider-key-abc"
	raw := fmt.Sprintf(`upstream body contains %s in error`, key)
	safe := providervalid.RedactString(raw, key)
	if providervalid.ContainsSecret(safe, key) {
		t.Fatal("leaked")
	}
}

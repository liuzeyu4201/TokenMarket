package chatcompat_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestRedactionStripsKeyAndNotInRef(t *testing.T) {
	key := "sk-synthetic-test-key-not-real"
	errBody := "upstream said " + key + " is bad; user said hello world"
	out := chatcompat.RedactString(errBody, key)
	if chatcompat.ContainsSecret(out, key) {
		t.Fatal(out)
	}
	ref := chatcompat.CredentialRef(key, "test-secret")
	if ref == "" || chatcompat.ContainsSecret(ref, key) {
		t.Fatal(ref)
	}
	if chatcompat.CredentialRef(key, "test-secret") != ref {
		t.Fatal("unstable ref")
	}
}

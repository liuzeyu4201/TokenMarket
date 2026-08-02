package providervalid_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestCredentialRefStableAndIrreversible(t *testing.T) {
	key := "sk-synthetic-test-key-not-real"
	a := providervalid.CredentialRef(key, "secret")
	b := providervalid.CredentialRef(key, "secret")
	if a != b || a == "" {
		t.Fatalf("stable ref failed %q %q", a, b)
	}
	if a == key || providervalid.ContainsSecret(a, key) {
		t.Fatal("ref must not contain key")
	}
	if providervalid.CredentialRef(key, "other") == a {
		t.Fatal("different secret should differ")
	}
}

func TestRedactString(t *testing.T) {
	key := "sk-secret-value-xyz"
	msg := "Authorization Bearer " + key
	out := providervalid.RedactString(msg, key)
	if providervalid.ContainsSecret(out, key) {
		t.Fatalf("still contains key: %s", out)
	}
}

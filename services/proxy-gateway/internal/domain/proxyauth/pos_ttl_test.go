package proxyauth

import (
	"testing"
	"time"
)

func TestDefaultPositiveCacheTTLIsOneSecond(t *testing.T) {
	if defaultPosTTL != time.Second {
		t.Fatalf("defaultPosTTL=%s want 1s for revoke SLA", defaultPosTTL)
	}
}

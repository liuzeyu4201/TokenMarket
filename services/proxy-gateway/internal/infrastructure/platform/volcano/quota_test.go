package volcano_test

import (
	"context"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

func TestNoopQuotaReader(t *testing.T) {
	q, err := volcano.NoopQuotaReader{}.ReadQuota(context.Background(), "k")
	if err != nil || q.Available {
		t.Fatalf("%+v %v", q, err)
	}
}

func TestStubQuota(t *testing.T) {
	pos := volcano.NewPositiveStub("100", "CNY_fen")
	q, err := pos.ReadQuota(context.Background(), "k")
	if err != nil || !q.Available || q.Amount != "100" {
		t.Fatalf("%+v", q)
	}
	z := volcano.NewZeroStub("CNY_fen")
	q, err = z.ReadQuota(context.Background(), "k")
	if err != nil || q.Amount != "0" {
		t.Fatalf("%+v", q)
	}
}

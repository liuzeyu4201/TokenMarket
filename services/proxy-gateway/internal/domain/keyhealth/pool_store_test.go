package keyhealth_test

import (
	"context"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keyhealth"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keypool"
)

func TestPoolStoreListAndApply(t *testing.T) {
	p := keypool.New([]keypool.SellerKey{
		{ID: "a", APIKey: "k", Admin: "active", Health: "unknown"},
	}, 4)
	st := keyhealth.PoolStore{Pool: p}
	got := st.ListActive(context.Background())
	if len(got) != 1 || got[0].ID != "a" {
		t.Fatalf("%v", got)
	}
	if err := st.ApplyHealth(context.Background(), "a", "healthy"); err != nil {
		t.Fatal(err)
	}
	if p.Snapshot()[0].Health != "healthy" {
		t.Fatal(p.Snapshot()[0].Health)
	}
}

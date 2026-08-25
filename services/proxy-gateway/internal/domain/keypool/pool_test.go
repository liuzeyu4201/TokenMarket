package keypool_test

import (
	"context"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keypool"
)

func TestRoundRobinSkipsUnhealthyAndPaused(t *testing.T) {
	p := keypool.New([]keypool.SellerKey{
		{ID: "a", APIKey: "k1", Admin: "active", Health: "healthy"},
		{ID: "b", APIKey: "k2", Admin: "paused", Health: "healthy"},
		{ID: "c", APIKey: "k3", Admin: "active", Health: "down"},
		{ID: "d", APIKey: "k4", Admin: "active", Health: "healthy"},
	}, 8)
	var ids []string
	for i := 0; i < 4; i++ {
		k, ok := p.Pick("")
		if !ok {
			t.Fatal("pick")
		}
		ids = append(ids, k.ID)
		p.Release(k.ID)
	}
	for _, id := range ids {
		if id == "b" || id == "c" {
			t.Fatalf("picked non-routable %s", id)
		}
	}
}

func TestCapacityRejects(t *testing.T) {
	p := keypool.New([]keypool.SellerKey{
		{ID: "a", APIKey: "k", Admin: "active", Health: "healthy"},
	}, 1)
	if _, ok := p.Pick(""); !ok {
		t.Fatal("first")
	}
	if _, ok := p.Pick(""); ok {
		t.Fatal("over capacity")
	}
	p.Release("a")
	if _, ok := p.Pick(""); !ok {
		t.Fatal("after release")
	}
}

func TestRoutable(t *testing.T) {
	if keypool.Routable(keypool.SellerKey{Admin: "active", Health: "unknown"}) {
		t.Fatal("unknown not routable")
	}
}

func TestPickExcludesBuyerOwnedSellerKey(t *testing.T) {
	p := keypool.New([]keypool.SellerKey{
		{ID: "mine", SellerID: "buyer-1", APIKey: "k1", Admin: "active", Health: "healthy"},
		{ID: "other", SellerID: "seller-9", APIKey: "k2", Admin: "active", Health: "healthy"},
	}, 8)
	k, ok := p.Pick("buyer-1")
	if !ok || k.ID != "other" {
		t.Fatalf("got %+v ok=%v", k, ok)
	}
}

func TestUpdateHealthRemovesFromPick(t *testing.T) {
	p := keypool.New([]keypool.SellerKey{
		{ID: "a", SellerID: "s", APIKey: "k", Admin: "active", Health: "healthy"},
	}, 8)
	p.UpdateHealth("a", "down")
	if _, ok := p.Pick(""); ok {
		t.Fatal("unhealthy still picked")
	}
}

func TestSnapshotReplaceAndDefaultInflight(t *testing.T) {
	p := keypool.New(nil, 0)
	if _, ok := p.Pick(""); ok {
		t.Fatal("empty")
	}
	p.ReplaceKey(keypool.SellerKey{ID: "n", SellerID: "s", APIKey: "k", Admin: "active", Health: "healthy"})
	got := p.Snapshot()
	if len(got) != 1 || got[0].ID != "n" {
		t.Fatalf("%+v", got)
	}
	p.ReplaceKey(keypool.SellerKey{ID: "n", SellerID: "s", APIKey: "k2", Admin: "active", Health: "healthy"})
	if p.Snapshot()[0].APIKey != "k2" {
		t.Fatal("replace")
	}
	if err := p.Refresh(context.Background()); err != nil {
		t.Fatal(err)
	}
}

type errSrc struct{}

func (errSrc) List(context.Context) ([]keypool.SellerKey, error) {
	return nil, errString("nope")
}

type errString string

func (e errString) Error() string { return string(e) }

func TestRefreshError(t *testing.T) {
	p := keypool.NewFromSource(errSrc{}, 2)
	if err := p.Refresh(context.Background()); err == nil {
		t.Fatal("want err")
	}
}

func TestPickSkipsZeroQuota(t *testing.T) {
	p := keypool.New([]keypool.SellerKey{
		{ID: "zero", Admin: "active", Health: "healthy", RemainingQuota: "0"},
		{ID: "ok", Admin: "active", Health: "healthy", RemainingQuota: "10"},
	}, 8)
	k, ok := p.Pick("")
	if !ok || k.ID != "ok" {
		t.Fatalf("got %+v ok=%v", k, ok)
	}
}

func TestCooldownBlocksThenExpires(t *testing.T) {
	p := keypool.New([]keypool.SellerKey{
		{ID: "a", Admin: "active", Health: "healthy"},
	}, 8)
	p.Cooldown("a", 50*time.Millisecond)
	if _, ok := p.Pick(""); ok {
		t.Fatal("cooldown should block")
	}
	time.Sleep(60 * time.Millisecond)
	if _, ok := p.Pick(""); !ok {
		t.Fatal("cooldown expired")
	}
}

func TestAllocableConcurrencyEightyPercent(t *testing.T) {
	if keypool.AllocableConcurrency(10) != 8 {
		t.Fatal(keypool.AllocableConcurrency(10))
	}
	if keypool.AllocableConcurrency(1) != 1 {
		t.Fatal("min 1")
	}
	if keypool.AllocableConcurrency(0) != 32 {
		t.Fatal("unknown official uses conservative 32")
	}
}

func TestRefreshFromSource(t *testing.T) {
	src := keypool.StaticSource{Keys: []keypool.SellerKey{
		{ID: "n", SellerID: "s", APIKey: "k", Admin: "active", Health: "healthy"},
	}}
	p := keypool.NewFromSource(src, 2)
	if err := p.Refresh(context.Background()); err != nil {
		t.Fatal(err)
	}
	k, ok := p.Pick("")
	if !ok || k.ID != "n" {
		t.Fatal(k, ok)
	}
}

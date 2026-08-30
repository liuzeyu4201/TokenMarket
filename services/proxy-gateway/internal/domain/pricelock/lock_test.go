package pricelock_test

import (
	"sync"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/pricelock"
)

func TestLockCopiesCurrentSnapshot(t *testing.T) {
	l := pricelock.NewLocker()
	l.Publish(pricelock.Snapshot{RateVersion: "rv-1", BuyerBPS: 12000, SellerBPS: 10000})
	s, ok := l.Lock("r1")
	if !ok || s.RateVersion != "rv-1" || s.BuyerBPS != 12000 {
		t.Fatalf("%+v %v", s, ok)
	}
	l.Publish(pricelock.Snapshot{RateVersion: "rv-2", BuyerBPS: 15000, SellerBPS: 10000})
	got, _ := l.Get("r1")
	if got.RateVersion != "rv-1" || got.BuyerBPS != 12000 {
		t.Fatalf("lock rewritten %+v", got)
	}
	s2, _ := l.Lock("r2")
	if s2.RateVersion != "rv-2" {
		t.Fatalf("%+v", s2)
	}
}

func TestLockIdempotent(t *testing.T) {
	l := pricelock.NewLocker()
	l.Publish(pricelock.Snapshot{RateVersion: "rv-1", BuyerBPS: 1, SellerBPS: 1})
	a, _ := l.Lock("r")
	l.Publish(pricelock.Snapshot{RateVersion: "rv-2", BuyerBPS: 2, SellerBPS: 2})
	b, _ := l.Lock("r")
	if a != b || b.RateVersion != "rv-1" {
		t.Fatalf("%+v %+v", a, b)
	}
}

func TestLockFailClosedWithoutPublish(t *testing.T) {
	l := pricelock.NewLocker()
	if _, ok := l.Lock("r"); ok {
		t.Fatal("expected fail closed")
	}
}

func TestConcurrentLockAndPublish(t *testing.T) {
	l := pricelock.NewLocker()
	l.Publish(pricelock.Snapshot{RateVersion: "rv-1", BuyerBPS: 12000, SellerBPS: 9000})
	var wg sync.WaitGroup
	got := make([]pricelock.Snapshot, 64)
	wg.Add(65)
	go func() {
		defer wg.Done()
		l.Publish(pricelock.Snapshot{RateVersion: "rv-2", BuyerBPS: 15000, SellerBPS: 9000})
	}()
	for i := 0; i < 64; i++ {
		i := i
		go func() {
			defer wg.Done()
			s, ok := l.Lock("req")
			if ok {
				got[i] = s
			}
		}()
	}
	wg.Wait()
	var seen pricelock.Snapshot
	found := false
	for _, s := range got {
		if s.RateVersion == "" {
			continue
		}
		if !found {
			seen = s
			found = true
			continue
		}
		if s != seen {
			t.Fatalf("mixed snapshots %+v vs %+v", seen, s)
		}
	}
	if !found {
		t.Fatal("no lock")
	}
	if seen.RateVersion == "rv-1" && seen.BuyerBPS != 12000 {
		t.Fatalf("%+v", seen)
	}
	if seen.RateVersion == "rv-2" && seen.BuyerBPS != 15000 {
		t.Fatalf("%+v", seen)
	}
}

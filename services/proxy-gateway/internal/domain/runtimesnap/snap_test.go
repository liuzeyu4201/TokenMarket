package runtimesnap_test

import (
	"sync"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/runtimesnap"
)

func loadCat(t *testing.T) *endpcatalog.Catalog {
	t.Helper()
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	return c
}

func TestSwapRejectsNilCatalog(t *testing.T) {
	var h runtimesnap.Holder
	if _, err := h.Swap("v1", nil); err == nil {
		t.Fatal("expected reject")
	}
}

func TestPinSurvivesSwap(t *testing.T) {
	var h runtimesnap.Holder
	c := loadCat(t)
	if _, err := h.Swap("v1", c); err != nil {
		t.Fatal(err)
	}
	pin := h.Pin()
	if pin == nil || pin.ID != "v1" {
		t.Fatalf("%+v", pin)
	}
	if _, err := h.Swap("v2", c); err != nil {
		t.Fatal(err)
	}
	if pin.ID != "v1" || pin.Generation != 1 {
		t.Fatalf("pin mutated %+v", pin)
	}
	cur := h.Current()
	if cur.ID != "v2" || cur.Generation != 2 {
		t.Fatalf("%+v", cur)
	}
}

func TestConcurrentPinSeesSingleGeneration(t *testing.T) {
	var h runtimesnap.Holder
	c := loadCat(t)
	if _, err := h.Swap("start", c); err != nil {
		t.Fatal(err)
	}
	var wg sync.WaitGroup
	seen := make([]uint64, 64)
	for i := 0; i < 64; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			p := h.Pin()
			seen[i] = p.Generation
			d := endpcatalog.Admit(p.Catalog, endpcatalog.AdmitInput{
				Provider:    "openai",
				Method:      "POST",
				Path:        "/v1/chat/completions",
				ProjectMode: "shared",
			})
			if !d.Allow {
				t.Errorf("admit %s", d.Code)
			}
		}(i)
	}
	if _, err := h.Swap("next", c); err != nil {
		t.Fatal(err)
	}
	wg.Wait()
	for i, g := range seen {
		if g != 1 && g != 2 {
			t.Fatalf("request %d mixed generation %d", i, g)
		}
	}
}

func TestTwoHoldersIdenticalAdmit(t *testing.T) {
	c := loadCat(t)
	var a, b runtimesnap.Holder
	if _, err := a.Swap("a", c); err != nil {
		t.Fatal(err)
	}
	if _, err := b.Swap("b", c); err != nil {
		t.Fatal(err)
	}
	in := endpcatalog.AdmitInput{Provider: "openai", Method: "GET", Path: "/v1/organization/users"}
	da := endpcatalog.Admit(a.Pin().Catalog, in)
	db := endpcatalog.Admit(b.Pin().Catalog, in)
	if da.Code != db.Code || da.Allow != db.Allow {
		t.Fatalf("%+v vs %+v", da, db)
	}
	if da.Code != endpcatalog.CodeControlPlane {
		t.Fatal(da.Code)
	}
}

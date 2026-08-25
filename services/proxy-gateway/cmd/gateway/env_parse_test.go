package main

import (
	"context"
	"net/http"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keypool"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/proxyauth"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

func TestPublishInventoryFromPool(t *testing.T) {
	p := keypool.New([]keypool.SellerKey{
		{ID: "a", Admin: "active", Health: "healthy"},
		{ID: "b", Admin: "paused", Health: "down"},
	}, 4)
	inv := observability.NewKeyInventoryMetrics()
	reg := prometheus.NewPedanticRegistry()
	inv.MustRegister(reg)
	publishInventory(inv, p)
	mfs, err := reg.Gather()
	if err != nil {
		t.Fatal(err)
	}
	var routable float64
	for _, mf := range mfs {
		if mf.GetName() != "provider_key_inventory" {
			continue
		}
		for _, metric := range mf.Metric {
			for _, lp := range metric.GetLabel() {
				if lp.GetName() == "status" && lp.GetValue() == "routable" {
					routable = metric.GetGauge().GetValue()
				}
			}
		}
	}
	if routable != 1 {
		t.Fatalf("routable %v", routable)
	}
}

func TestParseSellerKeysPipe(t *testing.T) {
	keys := parseSellerKeysEnv("id1|seller-a|sk-abc:with:colons|active|healthy|10")
	if len(keys) != 1 || keys[0].APIKey != "sk-abc:with:colons" || keys[0].SellerID != "seller-a" {
		t.Fatalf("%+v", keys)
	}
	if keys[0].OfficialConcurrency != 10 || keys[0].MaxInflight != 8 {
		t.Fatalf("80%% of official 10: %+v", keys[0])
	}
}

func TestParseProxyAuthRequiresTmk(t *testing.T) {
	pepper := []byte("p")
	sec := "tmk-0123456789abcdef0123456789abcdef"
	got := parseProxyAuthEnv(pepper, sec+"|buyer-1,tm_pk_notvalid|buyer-2")
	if len(got) != 1 {
		t.Fatalf("%d", len(got))
	}
	h := proxyauth.HashSecret(pepper, sec)
	if got[h].BuyerID != "buyer-1" {
		t.Fatalf("%+v", got)
	}
}

func TestListenServeStopsOnCancel(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	errc := make(chan error, 1)
	go func() {
		errc <- listenServe(ctx, "127.0.0.1:0", http.NotFoundHandler())
	}()
	time.Sleep(40 * time.Millisecond)
	cancel()
	select {
	case err := <-errc:
		if err != nil {
			t.Fatal(err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("listenServe did not stop")
	}
}

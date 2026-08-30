package passthrough

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/pricelock"
)

func TestKernelLocksPriceOnAdmit(t *testing.T) {
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	t.Cleanup(up.Close)
	locker := pricelock.NewLocker()
	locker.Publish(pricelock.Snapshot{RateVersion: "rv-1", BuyerBPS: 12000, SellerBPS: 10000})
	k := &Kernel{
		Catalog:   testCatalog(),
		Selector:  StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}},
		PriceLock: locker,
	}
	req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
	req.Header.Set("X-Request-ID", "rid-lock-1")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	got, ok := locker.Get("rid-lock-1")
	if !ok || got.RateVersion != "rv-1" || got.BuyerBPS != 12000 {
		t.Fatalf("%+v %v status=%d", got, ok, rec.Code)
	}
	locker.Publish(pricelock.Snapshot{RateVersion: "rv-2", BuyerBPS: 15000, SellerBPS: 10000})
	again, _ := locker.Get("rid-lock-1")
	if again.RateVersion != "rv-1" {
		t.Fatalf("rewritten %+v", again)
	}
}

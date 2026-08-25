package apisvc_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageobs"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/apisvc"
)

func TestListAndLookupAndObserve(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/internal/v1/seller-keys/routable", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Internal-Token") != "tok" {
			w.WriteHeader(401)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code": "0",
			"data": []map[string]string{{
				"id": "k1", "seller_id": "s1", "api_key": "sk-syn",
				"administrative_state": "active", "health_state": "healthy", "platform": "volcano",
			}},
		})
	})
	mux.HandleFunc("/internal/v1/proxy-keys/by-hash", func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code": "0",
			"data": map[string]string{"key_id": "pk", "buyer_id": "b1", "platform": "volcano", "status": "active"},
		})
	})
	mux.HandleFunc("/internal/v1/usage-observations", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_ = json.NewEncoder(w).Encode(map[string]string{"code": "0"})
	})
	mux.HandleFunc("/internal/v1/seller-keys/k1/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_ = json.NewEncoder(w).Encode(map[string]string{"code": "0"})
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()
	c := apisvc.New(srv.URL, "tok")
	keys, err := c.List(context.Background())
	if err != nil || len(keys) != 1 || keys[0].APIKey != "sk-syn" {
		t.Fatalf("%v %v", keys, err)
	}
	rec, ok := c.Lookup("abc")
	if !ok || rec.BuyerID != "b1" {
		t.Fatalf("%v %v", rec, ok)
	}
	if err := c.Observe(context.Background(), usageobs.Observation{RequestID: "r"}); err != nil {
		t.Fatal(err)
	}
	if err := c.PatchHealth(context.Background(), "k1", "healthy"); err != nil {
		t.Fatal(err)
	}
}

func TestLookupFailClosed(t *testing.T) {
	c := apisvc.New("", "")
	if _, ok := c.Lookup("x"); ok {
		t.Fatal("disabled must fail closed")
	}
}

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
				"official_concurrency": "10",
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
	if keys[0].OfficialConcurrency != 10 || keys[0].MaxInflight != 8 {
		t.Fatalf("list must set 80%% cap: %+v", keys[0])
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

func TestFetchRouteSnapshotFailClosedAndHydrates(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/internal/v1/projects/proj-1/route-snapshot", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Internal-Token") != "tok" {
			w.WriteHeader(401)
			return
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code": "0",
			"data": map[string]any{
				"project_id":     "proj-1",
				"mode":           "shared",
				"preview_opt_in": true,
				"buyer_owner_id": "buyer-1",
				"connections": []map[string]string{{
					"connection_id": "c1", "provider": "openai", "protocol": "openai",
					"supply_mode": "shared", "base_url": "https://api.openai.com",
					"credential": "sk-live", "seller_owner_id": "seller-9",
					"health": "healthy", "lifecycle": "listed",
				}},
			},
		})
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()
	c := apisvc.New(srv.URL, "tok")
	snap, ok := c.FetchRouteSnapshot("proj-1")
	if !ok || snap.Mode != "shared" || !snap.PreviewOptIn || len(snap.Connections) != 1 {
		t.Fatalf("%+v %v", snap, ok)
	}
	if snap.Connections[0].Credential != "sk-live" {
		t.Fatal("internal snapshot must include dataplane credential")
	}
	missing, ok := c.FetchRouteSnapshot("nope")
	if ok || missing.ProjectID != "" {
		t.Fatal("missing project must fail closed")
	}
	disabled := apisvc.New("", "")
	if _, ok := disabled.FetchRouteSnapshot("proj-1"); ok {
		t.Fatal("disabled client must fail closed")
	}
}

func TestLookupFailClosed(t *testing.T) {
	c := apisvc.New("", "")
	if _, ok := c.Lookup("x"); ok {
		t.Fatal("disabled must fail closed")
	}
}

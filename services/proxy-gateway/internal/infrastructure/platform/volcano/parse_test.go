package volcano_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

func TestListModelsEmptyData(t *testing.T) {
	body := readFixture(t, "models_empty.json")
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_, _ = w.Write(body)
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	res := c.ListModels(context.Background(), "k")
	if !res.AuthOK {
		t.Fatalf("%+v", res)
	}
	if len(res.ModelIDs) != 0 {
		t.Fatalf("ids %v", res.ModelIDs)
	}
}

func TestStubQuotaError(t *testing.T) {
	s := volcano.StubQuotaReader{Err: volcano.ErrQuota}
	_, err := s.ReadQuota(context.Background(), "k")
	if err == nil {
		t.Fatal("expected err")
	}
}

func TestListModelsMissingDataField(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"object":"list"}`))
	}))
	defer srv.Close()
	c := volcano.NewModelsClient(srv.URL, 5, 300)
	res := c.ListModels(context.Background(), "k")
	// missing data → invalid_response
	if res.AuthOK {
		t.Fatalf("should not auth ok: %+v", res)
	}
}

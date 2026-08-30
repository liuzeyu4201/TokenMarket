package passthrough

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageobs"
)

func TestMeteringEndEventIdempotent(t *testing.T) {
	k, _, _ := kernelAgainst(t, func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	})
	sink := usageobs.NewMemorySink()
	k.Usage = sink
	for i := 0; i < 2; i++ {
		req := httptest.NewRequest(http.MethodPost, "/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
		req.Header.Set("X-Request-ID", "same-rid")
		rec := httptest.NewRecorder()
		k.ServeHTTP(rec, req, "shared", false)
		if rec.Code != 200 {
			t.Fatalf("status %d", rec.Code)
		}
	}
	if sink.Len() != 1 {
		t.Fatalf("expected 1 observation got %d", sink.Len())
	}
}

package passthrough

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

func TestNoUpstreamIncrementsNoCandidate(t *testing.T) {
	reg := prometheus.NewPedanticRegistry()
	m := observability.NewSLOMetrics()
	m.MustRegister(reg)
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: FailClosedSelector{},
		SLO:      m,
	}
	req := httptest.NewRequest(http.MethodPost, "/v1/chat/completions", strings.NewReader(`{}`))
	req.Header.Set("Content-Type", "application/json")
	rec := httptest.NewRecorder()
	k.ServeHTTP(rec, req, "shared", false)
	mfs, err := reg.Gather()
	if err != nil {
		t.Fatal(err)
	}
	for _, mf := range mfs {
		if mf.GetName() == "proxy_route_no_candidate_total" {
			if mf.Metric[0].GetCounter().GetValue() < 1 {
				t.Fatal("expected no-candidate increment")
			}
			return
		}
	}
	t.Fatal("missing no-candidate metric")
}

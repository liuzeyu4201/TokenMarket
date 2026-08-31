package observability_test

import (
	"strings"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

func TestTraceCorrelateFiveHops(t *testing.T) {
	log := observability.NewTraceLog()
	rid := "rid-go-1"
	stages := []string{"proxy", "route", "upstream", "usage", "ledger"}
	for _, stage := range stages {
		kind := "span"
		if stage == "usage" || stage == "ledger" {
			kind = "link"
		}
		log.Append(observability.Hop{
			RequestID: rid,
			Service:   "gateway",
			Stage:     stage,
			Kind:      kind,
			Freshness: "live",
			At:        time.Date(2026, 8, 31, 0, 0, 0, 0, time.UTC),
		})
	}
	got := log.Correlate(rid)
	if len(got) != 5 {
		t.Fatalf("hops %d", len(got))
	}
	if got[3].Kind != "link" || got[4].Kind != "link" {
		t.Fatalf("async hops must be links")
	}
}

func TestSLOMetricsBoundedAndSplitLatency(t *testing.T) {
	reg := prometheus.NewPedanticRegistry()
	m := observability.NewSLOMetrics()
	m.MustRegister(reg)
	m.ObserveRED("dataplane", "openai", "chat", "200", 10*time.Millisecond, 80*time.Millisecond)
	m.ObserveStream("openai", "connect", 5*time.Millisecond, "")
	m.ObserveStream("openai", "first_event", 12*time.Millisecond, "")
	m.ObserveStream("openai", "duration", 2*time.Second, "complete")
	m.ObserveNoCandidate()
	m.SetBacklog(3)
	m.SetUnresolved(4)
	m.SetConnectionHealth("unhealthy", 1)
	if observability.AllowLabels(map[string]string{"user_id": "u1"}) {
		t.Fatal("user_id label must be rejected")
	}
	mfs, err := reg.Gather()
	if err != nil {
		t.Fatal(err)
	}
	names := map[string]bool{}
	for _, mf := range mfs {
		names[mf.GetName()] = true
		for _, metric := range mf.Metric {
			for _, lp := range metric.GetLabel() {
				if lp.GetName() == "request_id" || lp.GetName() == "user_id" {
					t.Fatalf("high cardinality %s", lp.GetName())
				}
			}
		}
	}
	for _, want := range []string{
		"proxy_slo_requests_total",
		"proxy_platform_duration_seconds",
		"proxy_upstream_duration_seconds",
		"proxy_stream_first_event_seconds",
		"proxy_route_no_candidate_total",
		"proxy_event_backlog",
		"proxy_unresolved_total",
	} {
		if !names[want] {
			t.Fatalf("missing %s", want)
		}
	}
}

func TestRedactScanZeroHits(t *testing.T) {
	safe := `{"request_id":"rid","authorization":"[redacted]"}`
	if hits := observability.ScanSecrets(safe); len(hits) != 0 {
		t.Fatalf("hits %v", hits)
	}
	if hits := observability.ScanSecrets("sk-live-secret api_key=x"); len(hits) == 0 {
		t.Fatal("expected hits")
	}
	if strings.Contains(observability.Redact("token=sk-live"), "sk-live") {
		t.Fatal("secret leaked")
	}
}

func TestCardinalityCap(t *testing.T) {
	g := observability.NewLabelGuard(2)
	if !g.Allow(map[string]string{"protocol": "openai", "endpoint": "a"}) {
		t.Fatal("first")
	}
	if !g.Allow(map[string]string{"protocol": "openai", "endpoint": "b"}) {
		t.Fatal("second")
	}
	if g.Allow(map[string]string{"protocol": "openai", "endpoint": "c"}) {
		t.Fatal("cap exceeded must reject")
	}
}

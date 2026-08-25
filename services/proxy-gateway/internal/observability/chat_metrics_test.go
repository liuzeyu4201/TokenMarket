package observability_test

import (
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

func TestChatMetricsRegisterObserveTruncated(t *testing.T) {
	reg := prometheus.NewPedanticRegistry()
	m := observability.NewChatMetrics()
	m.MustRegister(reg)
	m.Observe("volcano", false, "success", 5*time.Millisecond)
	m.Observe("volcano", true, "truncated_stream", 8*time.Millisecond)
	m.Truncated()
	mfs, err := reg.Gather()
	if err != nil {
		t.Fatal(err)
	}
	var sawTotal, sawTrunc bool
	for _, mf := range mfs {
		switch mf.GetName() {
		case "provider_chat_total":
			sawTotal = true
			if len(mf.Metric) < 1 {
				t.Fatal("no total samples")
			}
		case "provider_chat_truncated_total":
			sawTrunc = true
			if mf.Metric[0].GetCounter().GetValue() != 1 {
				t.Fatalf("trunc %v", mf.Metric[0].GetCounter().GetValue())
			}
		}
	}
	if !sawTotal || !sawTrunc {
		t.Fatalf("metrics missing total=%v trunc=%v", sawTotal, sawTrunc)
	}
}

func TestProxyHTTPMetricsBoundedLabels(t *testing.T) {
	reg := prometheus.NewPedanticRegistry()
	m := observability.NewProxyHTTPMetrics()
	m.MustRegister(reg)
	m.ObserveRequest("volcano", "false", "success", time.Millisecond)
	m.ObserveRequest("volcano", "true", "client_error", 2*time.Millisecond)
	m.AuthFail()
	m.CapacityReject()
	m.Usage("accepted")
	m.Health("volcano", "healthy")
	mfs, err := reg.Gather()
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]bool{
		"proxy_requests_total": false, "proxy_request_duration_seconds": false,
		"proxy_capacity_rejected_total": false, "proxy_auth_failures_total": false,
		"provider_usage_observe_total": false, "provider_health_check_total": false,
	}
	for _, mf := range mfs {
		if _, ok := want[mf.GetName()]; ok {
			want[mf.GetName()] = true
		}
		for _, metric := range mf.Metric {
			for _, lp := range metric.GetLabel() {
				if lp.GetName() == "request_id" || lp.GetName() == "user_id" || lp.GetName() == "key_id" {
					t.Fatalf("high cardinality label %s", lp.GetName())
				}
			}
		}
	}
	for name, ok := range want {
		if !ok {
			t.Fatalf("missing %s", name)
		}
	}
	if observability.ResultClass(401) != "auth_error" || observability.ResultClass(503) != "no_capacity" {
		t.Fatal("result class")
	}
}

func TestResultClassAndNilSafe(t *testing.T) {
	cases := map[int]string{401: "auth_error", 429: "rate_limited", 503: "no_capacity", 400: "client_error", 502: "system_error", 200: "success"}
	for st, want := range cases {
		if got := observability.ResultClass(st); got != want {
			t.Fatalf("%d %s != %s", st, got, want)
		}
	}
	var m *observability.ProxyHTTPMetrics
	m.ObserveRequest("", "false", "success", time.Millisecond)
	m.AuthFail()
	m.Health("", "healthy")
	if observability.NewLogger() == nil {
		t.Fatal("logger")
	}
}

func TestDefaultRegistries(t *testing.T) {
	if observability.DefaultChatMetrics() == nil {
		t.Fatal("chat")
	}
	if observability.DefaultProxyHTTPMetrics() == nil {
		t.Fatal("proxy")
	}
	if observability.DefaultValidateMetrics() == nil {
		t.Fatal("validate")
	}
	if observability.DefaultKeyInventoryMetrics() == nil {
		t.Fatal("inventory")
	}
}

func TestValidateMetricsObserve(t *testing.T) {
	reg := prometheus.NewPedanticRegistry()
	m := observability.NewValidateMetrics()
	m.MustRegister(reg)
	m.Observe("", "", time.Millisecond)
	m.GateRejected()
	var n *observability.ValidateMetrics
	n.Observe("volcano", "success", 0)
	n.GateRejected()
	n.MustRegister(reg)
}

func TestKeyInventoryPublishZerosStale(t *testing.T) {
	reg := prometheus.NewPedanticRegistry()
	g := observability.NewKeyInventoryMetrics()
	g.MustRegister(reg)
	g.Publish("volcano", []observability.KeyStatus{
		{Admin: "active", Health: "healthy"},
		{Admin: "paused", Health: "down"},
	})
	g.Publish("volcano", []observability.KeyStatus{
		{Admin: "active", Health: "healthy"},
	})
	mfs, err := reg.Gather()
	if err != nil {
		t.Fatal(err)
	}
	var routable, paused float64
	for _, mf := range mfs {
		if mf.GetName() != "provider_key_inventory" {
			continue
		}
		for _, metric := range mf.Metric {
			var status string
			for _, lp := range metric.GetLabel() {
				if lp.GetName() == "status" {
					status = lp.GetValue()
				}
			}
			val := metric.GetGauge().GetValue()
			if status == "routable" {
				routable = val
			}
			if status == "paused" {
				paused = val
			}
		}
	}
	if routable != 1 {
		t.Fatalf("routable %v", routable)
	}
	if paused != 0 {
		t.Fatalf("stale paused %v", paused)
	}
}

func TestKeyInventoryGauges(t *testing.T) {
	reg := prometheus.NewPedanticRegistry()
	g := observability.NewKeyInventoryMetrics()
	g.MustRegister(reg)
	g.Set("volcano", "healthy", 3)
	g.Set("volcano", "paused", 1)
	mfs, err := reg.Gather()
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, mf := range mfs {
		if mf.GetName() == "provider_key_inventory" {
			found = true
			if len(mf.Metric) < 2 {
				t.Fatalf("want 2 status series got %d", len(mf.Metric))
			}
		}
	}
	if !found {
		t.Fatal("provider_key_inventory missing")
	}
}

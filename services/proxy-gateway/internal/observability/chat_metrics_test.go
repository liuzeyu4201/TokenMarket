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

func TestDefaultChatMetrics(t *testing.T) {
	if observability.DefaultChatMetrics() == nil {
		t.Fatal("chat")
	}
}

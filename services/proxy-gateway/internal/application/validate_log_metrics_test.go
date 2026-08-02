package application_test

import (
	"bytes"
	"context"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	dto "github.com/prometheus/client_model/go"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/concurrency"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

func TestValidateStructuredLogNoKey(t *testing.T) {
	var buf bytes.Buffer
	logger := slog.New(slog.NewJSONHandler(&buf, &slog.HandlerOptions{Level: slog.LevelInfo}))
	key := "sk-must-not-appear-in-logs-xyz"
	v := &application.Validator{
		Cfg:    testCfg(),
		Models: stubModels{res: volcano.ModelsResult{Category: providervalid.CategoryInvalid}},
		Quota:  volcano.NoopQuotaReader{},
		Gate:   concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:    time.Now,
		Logger: logger,
	}
	r := v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "volcano", APIKey: key, RequestID: "req-log-1",
	})
	if r.ErrorCategory != providervalid.CategoryInvalid {
		t.Fatalf("%s", r.ErrorCategory)
	}
	out := buf.String()
	if !strings.Contains(out, "provider_validate_complete") {
		t.Fatalf("missing log event: %s", out)
	}
	if !strings.Contains(out, "req-log-1") {
		t.Fatal("missing request_id")
	}
	if !strings.Contains(out, "error_category") {
		t.Fatal("missing error_category")
	}
	if strings.Contains(out, key) {
		t.Fatal("api_key leaked in log")
	}
}

func TestValidateMetricsUsesRequestPlatform(t *testing.T) {
	reg := prometheus.NewRegistry()
	m := observability.NewValidateMetrics()
	m.MustRegister(reg)
	v := &application.Validator{
		Cfg:     testCfg(),
		Models:  stubModels{},
		Quota:   volcano.NoopQuotaReader{},
		Gate:    concurrency.NewValidateGate(32, 1, "test-secret"),
		Now:     time.Now,
		Metrics: m,
		Logger:  slog.New(slog.NewTextHandler(ioDiscard{}, nil)),
	}
	_ = v.ValidateCredential(context.Background(), providervalid.CredentialValidationRequest{
		Platform: "openai", APIKey: "sk-x",
	})
	families, err := reg.Gather()
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, f := range families {
		if f.GetName() != "provider_validate_total" {
			continue
		}
		for _, met := range f.GetMetric() {
			labels := map[string]string{}
			for _, lp := range met.GetLabel() {
				labels[lp.GetName()] = lp.GetValue()
			}
			if labels["platform"] == "openai" && labels["error_category"] == "unsupported_platform" {
				found = true
			}
			if labels["platform"] == "volcano" && labels["error_category"] == "unsupported_platform" {
				t.Fatal("must not hardcode volcano for unsupported platform")
			}
		}
	}
	if !found {
		t.Fatalf("expected openai unsupported_platform metric, got %v", dumpMetrics(families))
	}
}

type ioDiscard struct{}

func (ioDiscard) Write(p []byte) (int, error) { return len(p), nil }

func dumpMetrics(fs []*dto.MetricFamily) string {
	var b strings.Builder
	for _, f := range fs {
		b.WriteString(f.GetName())
		b.WriteString(";")
	}
	return b.String()
}

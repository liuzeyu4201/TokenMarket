package usageparse_test

import (
	"encoding/json"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageparse"
)

func TestOpenAITokensAndCostReported(t *testing.T) {
	body := `{"id":"chatcmpl-1","usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15,"completion_tokens_details":{"reasoning_tokens":2},"cost":0.002}}`
	c := usageparse.ParseBody("openai", "mixed", body, false)
	if c.CostStatus != usageparse.StatusReported || c.SettlementBasis != usageparse.StatusReported {
		t.Fatalf("%+v", c)
	}
	if c.ReportedMinor == nil || *c.ReportedMinor != 2000 {
		t.Fatalf("minor %+v", c.ReportedMinor)
	}
	if c.Usage.InputTokens == nil || *c.Usage.InputTokens != 10 {
		t.Fatalf("in %+v", c.Usage.InputTokens)
	}
	if c.Usage.OutputTokens == nil || *c.Usage.OutputTokens != 5 {
		t.Fatal("out")
	}
	if c.Usage.ReasoningTokens == nil || *c.Usage.ReasoningTokens != 2 {
		t.Fatal("reasoning")
	}
	if !c.DualPresent {
		t.Fatal("dual")
	}
}

func TestAnthropicUsageRatedNotZeroCost(t *testing.T) {
	body := `{"id":"msg_1","type":"message","usage":{"input_tokens":11,"output_tokens":7,"cache_read_input_tokens":3,"cache_creation_input_tokens":1}}`
	c := usageparse.ParseBody("anthropic", "usage", body, false)
	if c.CostStatus != usageparse.StatusRated {
		t.Fatalf("%s", c.CostStatus)
	}
	if c.ReportedMinor != nil {
		t.Fatalf("cost filled %v", *c.ReportedMinor)
	}
	if c.Usage.InputTokens == nil || *c.Usage.InputTokens != 11 {
		t.Fatal("input")
	}
	if c.Usage.CacheReadTokens == nil || *c.Usage.CacheReadTokens != 3 {
		t.Fatal("cache")
	}
}

func TestVertexUsageMetadata(t *testing.T) {
	body := `{"usageMetadata":{"promptTokenCount":4,"candidatesTokenCount":6,"totalTokenCount":10,"thoughtsTokenCount":1}}`
	c := usageparse.ParseBody("vertex", "usage", body, false)
	if c.CostStatus != usageparse.StatusRated {
		t.Fatalf("%s", c.CostStatus)
	}
	if c.Usage.TotalTokens == nil || *c.Usage.TotalTokens != 10 {
		t.Fatalf("%+v", c.Usage)
	}
	if c.Usage.ReasoningTokens == nil || *c.Usage.ReasoningTokens != 1 {
		t.Fatal("thoughts")
	}
}

func TestMissingUsageUnresolvedNotZero(t *testing.T) {
	c := usageparse.ParseBody("openai", "usage", `{"id":"x","object":"chat.completion"}`, false)
	if c.CostStatus != usageparse.StatusUnresolved {
		t.Fatalf("%s", c.CostStatus)
	}
	if c.ReportedMinor != nil {
		t.Fatal("zero cost forged")
	}
	if c.Usage.InputTokens != nil || c.Usage.TotalTokens != nil {
		t.Fatal("zero tokens forged")
	}
	if c.UnresolvedReason != "missing_usage" {
		t.Fatalf("%s", c.UnresolvedReason)
	}
}

func TestNegativeTokensUnresolved(t *testing.T) {
	c := usageparse.ParseBody("openai", "usage", `{"usage":{"prompt_tokens":-1,"completion_tokens":1,"total_tokens":0}}`, false)
	if c.CostStatus != usageparse.StatusUnresolved || c.UnresolvedReason != "negative_usage" {
		t.Fatalf("%+v", c)
	}
	if c.ReportedMinor != nil {
		t.Fatal("cost")
	}
}

func TestNegativeCostUnresolved(t *testing.T) {
	c := usageparse.ParseBody("openai", "mixed", `{"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2},"cost":-0.4}`, false)
	if c.CostStatus != usageparse.StatusUnresolved {
		t.Fatalf("%s %s", c.CostStatus, c.UnresolvedReason)
	}
	if c.ReportedMinor != nil {
		t.Fatal("negative stored")
	}
}

func TestReplaySameDigest(t *testing.T) {
	body := `{"usage":{"prompt_tokens":2,"completion_tokens":2,"total_tokens":4}}`
	a := usageparse.ParseBody("openai", "usage", body, false)
	b := usageparse.ParseBody("openai", "usage", body, false)
	if a.EvidenceDigest == "" || a.EvidenceDigest != b.EvidenceDigest {
		t.Fatalf("%s vs %s", a.EvidenceDigest, b.EvidenceDigest)
	}
	if a.ParserVersion != usageparse.ParserVersion {
		t.Fatal("parser")
	}
}

func TestMeteringNoneNotZero(t *testing.T) {
	c := usageparse.ParseBody("openai", "none", `{"id":"file-1"}`, false)
	if c.CostStatus != usageparse.StatusNone || c.SettlementBasis != usageparse.StatusNone {
		t.Fatalf("%+v", c)
	}
	if c.ReportedMinor != nil {
		t.Fatal("none must not settle 0")
	}
}

func TestSSEAnthropicMergesStartAndDelta(t *testing.T) {
	sse := "event: message_start\ndata: {\"type\":\"message_start\",\"message\":{\"usage\":{\"input_tokens\":9,\"output_tokens\":0}}}\n\n" +
		"event: message_delta\ndata: {\"type\":\"message_delta\",\"usage\":{\"output_tokens\":4}}\n\n" +
		"event: message_stop\ndata: {\"type\":\"message_stop\"}\n\n"
	c := usageparse.ParseBody("anthropic", "usage", sse, true)
	if c.Usage.InputTokens == nil || *c.Usage.InputTokens != 9 {
		t.Fatalf("input %+v", c.Usage.InputTokens)
	}
	if c.Usage.OutputTokens == nil || *c.Usage.OutputTokens != 4 {
		t.Fatalf("output %+v status=%s", c.Usage.OutputTokens, c.CostStatus)
	}
	if c.CostStatus != usageparse.StatusRated {
		t.Fatalf("%s", c.CostStatus)
	}
}

func TestSSEOpenAILastChunkUsage(t *testing.T) {
	sse := "data: {\"choices\":[{\"delta\":{\"content\":\"h\"}}]}\n\n" +
		"data: {\"usage\":{\"prompt_tokens\":3,\"completion_tokens\":1,\"total_tokens\":4}}\n\n" +
		"data: [DONE]\n\n"
	c := usageparse.ParseBody("openai", "usage", sse, true)
	if c.Usage.TotalTokens == nil || *c.Usage.TotalTokens != 4 {
		t.Fatalf("%+v", c)
	}
}

func TestPartialSSEDoesNotFillZero(t *testing.T) {
	sse := "data: {\"choices\":[{\"delta\":{\"content\":\"h\"}}]}\n\n"
	c := usageparse.ParseBody("openai", "usage", sse, true)
	if c.Usage.InputTokens != nil || c.ReportedMinor != nil {
		t.Fatalf("filled %+v", c)
	}
	if c.CostStatus != usageparse.StatusUnresolved {
		t.Fatalf("%s", c.CostStatus)
	}
}

func TestCaptureJSONOmitsSecrets(t *testing.T) {
	c := usageparse.ParseBody("openai", "usage", `{"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`, false)
	raw, err := json.Marshal(c)
	if err != nil {
		t.Fatal(err)
	}
	if usageparse.Forbidden(raw) {
		t.Fatalf("%s", raw)
	}
}

func TestStableCatalogMeteringStrategy(t *testing.T) {
	cat, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		t.Fatal(err)
	}
	allowed := map[string]struct{}{"usage": {}, "mixed": {}, "reported_cost": {}, "none": {}, "unresolved": {}}
	n := 0
	for _, rec := range cat.Records {
		if rec.Stability != "stable" {
			continue
		}
		n++
		if _, ok := allowed[rec.MeteringSource]; !ok {
			t.Fatalf("%s metering %q", rec.ID, rec.MeteringSource)
		}
		c := usageparse.ParseBody(rec.Provider, rec.MeteringSource, `{}`, false)
		switch rec.MeteringSource {
		case "none":
			if c.CostStatus != usageparse.StatusNone || c.ReportedMinor != nil {
				t.Fatalf("%s none %+v", rec.ID, c)
			}
		default:
			if rec.MeteringSource == "usage" || rec.MeteringSource == "mixed" || rec.MeteringSource == "reported_cost" {
				if c.CostStatus != usageparse.StatusUnresolved {
					t.Fatalf("%s empty body should unresolved got %s", rec.ID, c.CostStatus)
				}
				if c.ReportedMinor != nil {
					t.Fatalf("%s forged cost", rec.ID)
				}
			}
		}
	}
	if n < 1 {
		t.Fatal("no stable")
	}
}

func TestReportedCostStrategy(t *testing.T) {
	c := usageparse.ParseBody("openai", "reported_cost", `{"cost":1.5}`, false)
	if c.CostStatus != usageparse.StatusReported || c.ReportedMinor == nil {
		t.Fatalf("%+v", c)
	}
	c = usageparse.ParseBody("openai", "reported_cost", `{"id":"x"}`, false)
	if c.CostStatus != usageparse.StatusUnresolved || c.UnresolvedReason != "missing_cost" {
		t.Fatalf("%+v", c)
	}
}

func TestCatalogUnresolvedStrategy(t *testing.T) {
	c := usageparse.ParseBody("openai", "unresolved", `{"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`, false)
	if c.CostStatus != usageparse.StatusUnresolved || c.UnresolvedReason != "catalog_unresolved" {
		t.Fatalf("%+v", c)
	}
}

func TestInvalidJSONUnresolved(t *testing.T) {
	c := usageparse.ParseBody("openai", "usage", `{not-json`, false)
	if c.CostStatus != usageparse.StatusUnresolved || c.Integrity != "failed" {
		t.Fatalf("%+v", c)
	}
	if c.ReportedMinor != nil {
		t.Fatal("forged")
	}
}

func TestCostObjectAndUnknownUnit(t *testing.T) {
	c := usageparse.ParseBody("openai", "mixed", `{"cost":{"amount":"0.01","currency":"usd"}}`, false)
	if c.CostStatus != usageparse.StatusReported || c.Currency != "USD" || c.ReportedMinor == nil {
		t.Fatalf("%+v", c)
	}
	c = usageparse.ParseBody("openai", "mixed", `{"cost":"1e-3"}`, false)
	if c.CostStatus != usageparse.StatusUnresolved {
		t.Fatalf("sci %s %s", c.CostStatus, c.UnresolvedReason)
	}
}

func TestOverflowTokens(t *testing.T) {
	c := usageparse.ParseBody("openai", "usage", `{"usage":{"prompt_tokens":999999999999999999999,"completion_tokens":0,"total_tokens":0}}`, false)
	if c.CostStatus != usageparse.StatusUnresolved {
		t.Fatalf("%s", c.CostStatus)
	}
}

func TestNilRecorderAndEmptyRequestID(t *testing.T) {
	var m *usageparse.Memory
	m.Record(usageparse.Capture{RequestID: "x"})
	if m.Len() != 0 {
		t.Fatal("nil")
	}
	mem := usageparse.NewMemory()
	mem.Record(usageparse.Capture{CostStatus: usageparse.StatusNone})
	if mem.Len() != 1 {
		t.Fatal(mem.Len())
	}
}

func TestForbiddenFalseForNormalJSON(t *testing.T) {
	if usageparse.Forbidden([]byte(`{"cost_status":"rated"}`)) {
		t.Fatal("false positive")
	}
}

func TestMemoryRecorderIdempotent(t *testing.T) {
	m := usageparse.NewMemory()
	c := usageparse.ParseBody("openai", "usage", `{"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`, false)
	c.RequestID = "r1"
	m.Record(c)
	c2 := c
	c2.Usage.InputTokens = nil
	m.Record(c2)
	got, _ := m.Get("r1")
	if got.Usage.InputTokens == nil || *got.Usage.InputTokens != 1 {
		t.Fatalf("overwritten %+v", got)
	}
	if m.Len() != 1 {
		t.Fatal(m.Len())
	}
}

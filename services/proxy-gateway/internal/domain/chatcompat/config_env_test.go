package chatcompat_test

import (
	"context"
	"errors"
	"net"
	"os"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestLoadConfigFromEnv(t *testing.T) {
	t.Setenv("VOLCANO_CHAT_BASE_URL", "http://127.0.0.1:9/api/v3")
	t.Setenv("VOLCANO_V01_CHAT_MODELS", "doubao-pro-32k, doubao-lite-32k")
	t.Setenv("VOLCANO_CHAT_MODEL_MAP", "doubao-pro-32k=ep-1")
	t.Setenv("VOLCANO_CHAT_DEFAULT_DEADLINE_SECONDS", "60")
	t.Setenv("VOLCANO_CHAT_MAX_DEADLINE_SECONDS", "300")
	t.Setenv("VOLCANO_CHAT_MAX_BODY_BYTES", "4096")
	cfg, err := chatcompat.LoadConfigFromEnv()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.BaseURL != "http://127.0.0.1:9/api/v3" || len(cfg.Allowlist) != 2 {
		t.Fatalf("%+v", cfg)
	}
	if cfg.ModelMap["doubao-pro-32k"] != "ep-1" {
		t.Fatalf("%v", cfg.ModelMap)
	}
}

func TestLoadConfigUsesValidateBaseURL(t *testing.T) {
	os.Unsetenv("VOLCANO_CHAT_BASE_URL")
	t.Setenv("VOLCANO_VALIDATE_BASE_URL", "http://127.0.0.1:8/api/v3")
	t.Setenv("VOLCANO_V01_CHAT_MODELS", "doubao-pro-32k")
	cfg, err := chatcompat.LoadConfigFromEnv()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.BaseURL != "http://127.0.0.1:8/api/v3" {
		t.Fatal(cfg.BaseURL)
	}
}

func TestClassifyTransportAndCancel(t *testing.T) {
	if chatcompat.ClassifyTransport(nil) != chatcompat.CategoryTemporaryUnavailable {
		t.Fatal("nil")
	}
	if chatcompat.ClassifyTransport(context.DeadlineExceeded) != chatcompat.CategoryTimeout {
		t.Fatal("deadline")
	}
	if !chatcompat.IsCallerCancel(context.Canceled) {
		t.Fatal("cancel")
	}
	if chatcompat.IsCallerCancel(context.DeadlineExceeded) {
		t.Fatal("deadline not cancel")
	}
	var ne net.Error = timeoutErr{}
	if chatcompat.ClassifyTransport(ne) != chatcompat.CategoryTimeout {
		t.Fatal("net timeout")
	}
	if chatcompat.ClassifyTransport(errors.New("connection refused")) != chatcompat.CategoryTemporaryUnavailable {
		t.Fatal("conn")
	}
}

type timeoutErr struct{}

func (timeoutErr) Error() string   { return "timeout" }
func (timeoutErr) Timeout() bool   { return true }
func (timeoutErr) Temporary() bool { return true }

func TestSuggestedActionsAndRedactBody(t *testing.T) {
	if chatcompat.SuggestedActionFor(chatcompat.CategoryInvalid) != chatcompat.ActionFixCredential {
		t.Fatal("invalid")
	}
	if chatcompat.SuggestedActionFor(chatcompat.CategoryUnsupportedParameter) != chatcompat.ActionFixParameter {
		t.Fatal("param")
	}
	if chatcompat.SuggestedActionFor(chatcompat.CategoryRateLimited) != chatcompat.ActionRetryLater {
		t.Fatal("rl")
	}
	key := "sk-synthetic-test-key-not-real"
	long := key + string(make([]byte, 600))
	out := chatcompat.RedactBody(long, key)
	if chatcompat.ContainsSecret(out, key) {
		t.Fatal(out)
	}
	_ = time.Second
}

func TestValidateSamplingBoundsAndStop(t *testing.T) {
	bad := 3.0
	if chatcompat.ValidateSampling(chatcompat.ChatAdaptRequest{Temperature: &bad}) != chatcompat.CategoryUnsupportedParameter {
		t.Fatal("temp")
	}
	top := 0.0
	if chatcompat.ValidateSampling(chatcompat.ChatAdaptRequest{TopP: &top}) != chatcompat.CategoryUnsupportedParameter {
		t.Fatal("top")
	}
	if chatcompat.ValidateSampling(chatcompat.ChatAdaptRequest{Stop: []byte(`[]`)}) != chatcompat.CategoryUnsupportedParameter {
		t.Fatal("stop")
	}
	if chatcompat.ValidateMessages(nil) != chatcompat.CategoryUnsupportedParameter {
		t.Fatal("empty msgs")
	}
}

func TestParseRequestJSONSamplingFields(t *testing.T) {
	raw := []byte(`{"platform":"volcano","api_key":"sk-synthetic-test-key-not-real","model":"doubao-pro-32k","messages":[{"role":"user","content":"a"}],"max_tokens":16,"n":1,"stop":"END","presence_penalty":0.1,"frequency_penalty":-0.1,"stream":true}`)
	req, cat := chatcompat.ParseRequestJSON(raw)
	if cat != "" {
		t.Fatal(cat)
	}
	if req.MaxTokens == nil || *req.MaxTokens != 16 || req.N == nil || req.Stream == nil {
		t.Fatalf("%+v", req)
	}
	mmap := chatcompat.ModelMap{Allowlist: []string{"doubao-pro-32k"}}
	body, cat := chatcompat.FilterToProviderBody(req, mmap)
	if cat != "" {
		t.Fatal(cat)
	}
	if len(body) < 10 {
		t.Fatal("body")
	}
}

func TestPublicFromUpstreamFallback(t *testing.T) {
	m := chatcompat.ModelMap{Allowlist: []string{"doubao-pro-32k"}}
	if m.PublicFromUpstream("doubao-pro-32k", "") != "doubao-pro-32k" {
		t.Fatal("id")
	}
	if m.PublicFromUpstream("other", "doubao-pro-32k") != "doubao-pro-32k" {
		t.Fatal("req")
	}
}

func TestInspectUsagePartialMissing(t *testing.T) {
	p := 1
	st, u := chatcompat.InspectUsage(&p, nil, nil, true)
	if st != chatcompat.UsageMissing || u != nil {
		t.Fatal(st)
	}
	neg := -1
	c, tot := 1, 0
	st, _ = chatcompat.InspectUsage(&neg, &c, &tot, true)
	if st != chatcompat.UsageInconsistent {
		t.Fatal(st)
	}
}

func TestConfigValidateDeadline(t *testing.T) {
	if err := (chatcompat.Config{Allowlist: []string{"a"}, DefaultDeadlineSec: 0, MaxBodyBytes: 1}).Validate(); err == nil {
		t.Fatal("deadline")
	}
	if err := (chatcompat.Config{Allowlist: []string{"a"}, DefaultDeadlineSec: 1, MaxBodyBytes: 0}).Validate(); err == nil {
		t.Fatal("body")
	}
}

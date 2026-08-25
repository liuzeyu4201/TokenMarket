package chatcompat_test

import (
	"encoding/json"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestAllowlistAcceptsExtendedSampling(t *testing.T) {
	temp, maxTok, topP := 0.7, 128, 0.9
	n := 1
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real",
		Model: "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{
			{Role: "user", Content: json.RawMessage(`"hi"`)},
		},
		Temperature: &temp, MaxTokens: &maxTok, TopP: &topP, N: &n,
		Stop: json.RawMessage(`["END"]`),
	}
	if cat := chatcompat.ValidateSampling(req); cat != "" {
		t.Fatalf("sampling: %s", cat)
	}
	if cat := chatcompat.ValidateMessages(req.Messages); cat != "" {
		t.Fatalf("messages: %s", cat)
	}
}

func TestAllowlistRejectsToolsAndN2(t *testing.T) {
	raw := []byte(`{"platform":"volcano","api_key":"sk-synthetic-test-key-not-real","model":"doubao-pro-32k","messages":[{"role":"user","content":"hi"}],"tools":[]}`)
	if cat := chatcompat.ScanUnknownTopLevel(raw); cat != chatcompat.CategoryUnsupportedParameter {
		t.Fatalf("tools: %s", cat)
	}
	n := 2
	req := chatcompat.ChatAdaptRequest{N: &n}
	if cat := chatcompat.ValidateSampling(req); cat != chatcompat.CategoryUnsupportedParameter {
		t.Fatalf("n=2: %s", cat)
	}
	rf := []byte(`{"platform":"volcano","api_key":"x","model":"doubao-pro-32k","messages":[{"role":"user","content":"a"}],"response_format":{"type":"json_object"}}`)
	if cat := chatcompat.ScanUnknownTopLevel(rf); cat != chatcompat.CategoryUnsupportedParameter {
		t.Fatalf("response_format: %s", cat)
	}
}

func TestContentMultimodalNotRejected(t *testing.T) {
	content := json.RawMessage(`[{"type":"text","text":"see"},{"type":"image_url","image_url":{"url":"https://example.invalid/x.png"}}]`)
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: content}},
	}
	if cat := chatcompat.ValidateMessages(req.Messages); cat != "" {
		t.Fatalf("multimodal rejected: %s", cat)
	}
	body, cat := chatcompat.FilterToProviderBody(req, chatcompat.ModelMap{Allowlist: []string{"doubao-pro-32k"}})
	if cat != "" {
		t.Fatalf("filter: %s", cat)
	}
	if !json.Valid(body) {
		t.Fatal("invalid outbound")
	}
	s := string(body)
	if !contains(s, "image_url") {
		t.Fatalf("content not passed through: %s", s)
	}
}

func TestMessageToolCallsRejected(t *testing.T) {
	msg := json.RawMessage(`{"role":"assistant","content":"x","tool_calls":[]}`)
	if !chatcompat.MessageHasDisallowedKeys(msg) {
		t.Fatal("expected reject")
	}
	name := json.RawMessage(`{"role":"user","content":"x","name":"alice"}`)
	if !chatcompat.MessageHasDisallowedKeys(name) {
		t.Fatal("name should reject")
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(sub) == 0 || (len(s) > 0 && (indexOf(s, sub) >= 0)))
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}

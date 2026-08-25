package chatcompat_test

import (
	"encoding/json"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestFilterOutboundOnlyAllowlistKeys(t *testing.T) {
	raw := []byte(`{
		"platform":"volcano",
		"api_key":"sk-synthetic-test-key-not-real",
		"request_id":"qs-1",
		"model":"doubao-pro-32k",
		"temperature":0.5,
		"top_p":0.9,
		"messages":[{"role":"user","content":"hello"}]
	}`)
	req, cat := chatcompat.ParseRequestJSON(raw)
	if cat != "" {
		t.Fatal(cat)
	}
	body, cat := chatcompat.FilterToProviderBody(req, chatcompat.ModelMap{Allowlist: []string{"doubao-pro-32k"}})
	if cat != "" {
		t.Fatal(cat)
	}
	var obj map[string]json.RawMessage
	if err := json.Unmarshal(body, &obj); err != nil {
		t.Fatal(err)
	}
	for k := range obj {
		if _, ok := chatcompat.OutboundTopLevelKeys[k]; !ok {
			t.Fatalf("unexpected outbound key %s", k)
		}
	}
	if _, ok := obj["api_key"]; ok {
		t.Fatal("api_key leaked outbound")
	}
}

func TestFilterUnknownTopLevelDoesNotProduceBody(t *testing.T) {
	raw := []byte(`{"platform":"volcano","api_key":"sk-synthetic-test-key-not-real","model":"doubao-pro-32k","messages":[{"role":"user","content":"a"}],"seed":1}`)
	_, cat := chatcompat.ParseRequestJSON(raw)
	if cat != chatcompat.CategoryUnsupportedParameter {
		t.Fatalf("got %s", cat)
	}
}

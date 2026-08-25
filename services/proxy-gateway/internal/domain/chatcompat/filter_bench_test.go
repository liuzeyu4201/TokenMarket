package chatcompat_test

import (
	"encoding/json"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func BenchmarkFilterAndNormalize(b *testing.B) {
	raw := []byte(`{"platform":"volcano","api_key":"sk-synthetic-test-key-not-real","model":"doubao-pro-32k","messages":[{"role":"user","content":"hello"}],"temperature":0.7}`)
	mmap := chatcompat.ModelMap{Allowlist: []string{"doubao-pro-32k"}}
	up := []byte(`{"id":"1","choices":[{"index":0,"message":{"role":"assistant","content":"hi"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`)
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		req, cat := chatcompat.ParseRequestJSON(raw)
		if cat != "" {
			b.Fatal(cat)
		}
		if _, cat := chatcompat.FilterToProviderBody(req, mmap); cat != "" {
			b.Fatal(cat)
		}
		r := chatcompat.NormalizeNonStream(up, "doubao-pro-32k")
		if r.ErrorCategory != chatcompat.CategorySuccess {
			b.Fatal(r.ErrorCategory)
		}
	}
}

func BenchmarkNormalizeOnly(b *testing.B) {
	up := []byte(`{"id":"1","choices":[{"index":0,"message":{"role":"assistant","content":"hi"},"finish_reason":"stop"}],"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`)
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		_ = chatcompat.NormalizeNonStream(up, "doubao-pro-32k")
	}
	_ = json.RawMessage(nil)
}

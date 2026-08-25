package chatcompat

import (
	"encoding/json"
	"strings"
)

// FilterToProviderBody 将适配请求转为出站 JSON。失败返回类别且 body 为 nil。
func FilterToProviderBody(req ChatAdaptRequest, mmap ModelMap) ([]byte, ErrorCategory) {
	if cat := ScanUnknownTopLevel(req.Raw); cat != "" {
		return nil, cat
	}
	ep := strings.TrimSpace(req.Endpoint)
	if ep != "" && ep != "chat.completions" && ep != "chat/completions" {
		return nil, CategoryUnsupportedEndpoint
	}
	plat := strings.TrimSpace(req.Platform)
	if plat != "" && plat != "volcano" {
		return nil, CategoryUnsupportedPlatform
	}
	if strings.TrimSpace(req.APIKey) == "" {
		return nil, CategoryUnsupportedParameter
	}
	if cat := ValidateMessages(req.Messages); cat != "" {
		return nil, cat
	}
	if cat := ValidateSampling(req); cat != "" {
		return nil, cat
	}
	up, cat := mmap.ResolveOutbound(req.Model)
	if cat != "" {
		return nil, cat
	}

	out := map[string]any{"model": up, "messages": encodeMessages(req.Messages)}
	if req.Stream != nil {
		out["stream"] = *req.Stream
	}
	if req.Temperature != nil {
		out["temperature"] = *req.Temperature
	}
	if req.MaxTokens != nil {
		out["max_tokens"] = *req.MaxTokens
	}
	if req.TopP != nil {
		out["top_p"] = *req.TopP
	}
	if len(req.Stop) > 0 {
		var v any
		if err := json.Unmarshal(req.Stop, &v); err == nil {
			out["stop"] = v
		}
	}
	if req.PresencePenalty != nil {
		out["presence_penalty"] = *req.PresencePenalty
	}
	if req.FrequencyPenalty != nil {
		out["frequency_penalty"] = *req.FrequencyPenalty
	}
	if req.N != nil {
		out["n"] = *req.N
	}
	b, err := json.Marshal(out)
	if err != nil {
		return nil, CategoryUnsupportedParameter
	}
	// 再次保证出站键 ⊆ 允许列表
	var check map[string]json.RawMessage
	_ = json.Unmarshal(b, &check)
	for k := range check {
		if _, ok := OutboundTopLevelKeys[k]; !ok {
			return nil, CategoryUnsupportedParameter
		}
	}
	return b, ""
}

func encodeMessages(msgs []ChatMessage) []map[string]any {
	out := make([]map[string]any, 0, len(msgs))
	for _, m := range msgs {
		item := map[string]any{"role": m.Role}
		var content any
		if len(m.Content) > 0 {
			_ = json.Unmarshal(m.Content, &content)
		}
		item["content"] = content
		out = append(out, item)
	}
	return out
}

// ParseRequestJSON 从适配 JSON 构造请求（含 Raw 以便扫未知键与 message 额外键）。
func ParseRequestJSON(raw []byte) (ChatAdaptRequest, ErrorCategory) {
	if len(raw) > 0 {
		if cat := ScanUnknownTopLevel(raw); cat != "" {
			return ChatAdaptRequest{}, cat
		}
	}
	var obj map[string]json.RawMessage
	if err := json.Unmarshal(raw, &obj); err != nil {
		return ChatAdaptRequest{}, CategoryUnsupportedParameter
	}
	req := ChatAdaptRequest{Raw: raw}
	req.Platform = jsonString(obj["platform"])
	req.APIKey = jsonString(obj["api_key"])
	req.RequestID = jsonString(obj["request_id"])
	req.Endpoint = jsonString(obj["endpoint"])
	req.Model = jsonString(obj["model"])
	if v, ok := obj["stream"]; ok {
		var b bool
		if json.Unmarshal(v, &b) == nil {
			req.Stream = &b
		}
	}
	if v, ok := obj["temperature"]; ok {
		var f float64
		if json.Unmarshal(v, &f) == nil {
			req.Temperature = &f
		} else {
			return req, CategoryUnsupportedParameter
		}
	}
	if v, ok := obj["max_tokens"]; ok {
		var n int
		if json.Unmarshal(v, &n) == nil {
			req.MaxTokens = &n
		} else {
			return req, CategoryUnsupportedParameter
		}
	}
	if v, ok := obj["top_p"]; ok {
		var f float64
		if json.Unmarshal(v, &f) == nil {
			req.TopP = &f
		} else {
			return req, CategoryUnsupportedParameter
		}
	}
	if v, ok := obj["presence_penalty"]; ok {
		var f float64
		if json.Unmarshal(v, &f) == nil {
			req.PresencePenalty = &f
		} else {
			return req, CategoryUnsupportedParameter
		}
	}
	if v, ok := obj["frequency_penalty"]; ok {
		var f float64
		if json.Unmarshal(v, &f) == nil {
			req.FrequencyPenalty = &f
		} else {
			return req, CategoryUnsupportedParameter
		}
	}
	if v, ok := obj["n"]; ok {
		var n int
		if json.Unmarshal(v, &n) == nil {
			req.N = &n
		} else {
			return req, CategoryUnsupportedParameter
		}
	}
	if v, ok := obj["stop"]; ok {
		req.Stop = v
	}
	if v, ok := obj["messages"]; ok {
		var arr []json.RawMessage
		if err := json.Unmarshal(v, &arr); err != nil {
			return req, CategoryUnsupportedParameter
		}
		for _, item := range arr {
			if MessageHasDisallowedKeys(item) {
				return req, CategoryUnsupportedParameter
			}
			var m struct {
				Role    string          `json:"role"`
				Content json.RawMessage `json:"content"`
			}
			if err := json.Unmarshal(item, &m); err != nil {
				return req, CategoryUnsupportedParameter
			}
			req.Messages = append(req.Messages, ChatMessage{Role: m.Role, Content: m.Content})
		}
	}
	return req, ""
}

func jsonString(raw json.RawMessage) string {
	if len(raw) == 0 {
		return ""
	}
	var s string
	if json.Unmarshal(raw, &s) == nil {
		return s
	}
	return ""
}

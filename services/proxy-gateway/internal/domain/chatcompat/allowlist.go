package chatcompat

import (
	"encoding/json"
	"strings"
)

// AdapterTopLevelKeys 适配输入允许出现、但不出站的键。
var AdapterTopLevelKeys = map[string]struct{}{
	"platform": {}, "api_key": {}, "request_id": {}, "endpoint": {},
}

// OutboundTopLevelKeys 可写入火山 Chat Completions 体的顶层键。
var OutboundTopLevelKeys = map[string]struct{}{
	"model": {}, "messages": {}, "stream": {}, "temperature": {},
	"max_tokens": {}, "top_p": {}, "stop": {},
	"presence_penalty": {}, "frequency_penalty": {}, "n": {},
}

var allowedRoles = map[string]struct{}{
	"system": {}, "user": {}, "assistant": {},
}

// ScanUnknownTopLevel 扫描原始 JSON：未声明顶层键 → unsupported_parameter。
func ScanUnknownTopLevel(raw json.RawMessage) ErrorCategory {
	if len(raw) == 0 {
		return ""
	}
	var obj map[string]json.RawMessage
	if err := json.Unmarshal(raw, &obj); err != nil {
		return CategoryUnsupportedParameter
	}
	for k := range obj {
		if _, ok := AdapterTopLevelKeys[k]; ok {
			continue
		}
		if _, ok := OutboundTopLevelKeys[k]; ok {
			continue
		}
		return CategoryUnsupportedParameter
	}
	return ""
}

// ValidateMessages 校验 messages 结构（content 形态不校验）。
func ValidateMessages(msgs []ChatMessage) ErrorCategory {
	if len(msgs) == 0 || len(msgs) > 128 {
		return CategoryUnsupportedParameter
	}
	for _, m := range msgs {
		if _, ok := allowedRoles[strings.TrimSpace(m.Role)]; !ok {
			return CategoryUnsupportedParameter
		}
		if len(m.Content) == 0 || string(m.Content) == "null" {
			// 空 content 仍原样转发；null 也转发。不因形态拒绝。
			continue
		}
	}
	return ""
}

// ValidateSampling 校验扩展采样集取值；越界不钳制。
func ValidateSampling(req ChatAdaptRequest) ErrorCategory {
	if req.Temperature != nil {
		if *req.Temperature < 0 || *req.Temperature > 2 {
			return CategoryUnsupportedParameter
		}
	}
	if req.MaxTokens != nil && *req.MaxTokens < 1 {
		return CategoryUnsupportedParameter
	}
	if req.TopP != nil {
		if *req.TopP <= 0 || *req.TopP > 1 {
			return CategoryUnsupportedParameter
		}
	}
	if req.PresencePenalty != nil {
		if *req.PresencePenalty < -2 || *req.PresencePenalty > 2 {
			return CategoryUnsupportedParameter
		}
	}
	if req.FrequencyPenalty != nil {
		if *req.FrequencyPenalty < -2 || *req.FrequencyPenalty > 2 {
			return CategoryUnsupportedParameter
		}
	}
	if req.N != nil && *req.N != 1 {
		return CategoryUnsupportedParameter
	}
	if len(req.Stop) > 0 {
		if cat := validateStop(req.Stop); cat != "" {
			return cat
		}
	}
	return ""
}

func validateStop(raw json.RawMessage) ErrorCategory {
	var s string
	if err := json.Unmarshal(raw, &s); err == nil {
		if strings.TrimSpace(s) == "" {
			return CategoryUnsupportedParameter
		}
		return ""
	}
	var arr []string
	if err := json.Unmarshal(raw, &arr); err != nil {
		return CategoryUnsupportedParameter
	}
	if len(arr) < 1 || len(arr) > 4 {
		return CategoryUnsupportedParameter
	}
	for _, x := range arr {
		if strings.TrimSpace(x) == "" {
			return CategoryUnsupportedParameter
		}
	}
	return ""
}

// MessageHasDisallowedKeys 检查单条 message JSON 是否含 role/content 以外的键。
func MessageHasDisallowedKeys(msgJSON json.RawMessage) bool {
	var obj map[string]json.RawMessage
	if err := json.Unmarshal(msgJSON, &obj); err != nil {
		return true
	}
	for k := range obj {
		if k != "role" && k != "content" {
			return true
		}
	}
	return false
}

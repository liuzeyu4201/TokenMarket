package chatcompat

import (
	"encoding/json"
	"strings"
)

type upstreamChatJSON struct {
	ID      string `json:"id"`
	Object  string `json:"object"`
	Created int64  `json:"created"`
	Model   string `json:"model"`
	Choices []struct {
		Index        int             `json:"index"`
		FinishReason string          `json:"finish_reason"`
		Message      json.RawMessage `json:"message"`
	} `json:"choices"`
	Usage *struct {
		PromptTokens     *int `json:"prompt_tokens"`
		CompletionTokens *int `json:"completion_tokens"`
		TotalTokens      *int `json:"total_tokens"`
	} `json:"usage"`
}

// NormalizeNonStream 将上游 JSON 标准化为兼容结果。publicModel 为回写 ID。
func NormalizeNonStream(body []byte, publicModel string) ChatAdaptResult {
	var u upstreamChatJSON
	if err := json.Unmarshal(body, &u); err != nil {
		return fail(CategoryInvalidResponse)
	}
	if len(u.Choices) == 0 {
		return fail(CategoryInvalidResponse)
	}
	choices := make([]ChatChoice, 0, len(u.Choices))
	finish := ""
	for _, c := range u.Choices {
		choices = append(choices, ChatChoice{
			Index:        c.Index,
			FinishReason: c.FinishReason,
			Message:      c.Message,
		})
		if finish == "" {
			finish = c.FinishReason
		}
	}
	st := UsageNotApplicable
	var usage *Usage
	if u.Usage == nil {
		st = UsageMissing
	} else {
		st, usage = InspectUsage(u.Usage.PromptTokens, u.Usage.CompletionTokens, u.Usage.TotalTokens, true)
	}
	model := strings.TrimSpace(publicModel)
	if model == "" {
		model = u.Model
	}
	obj := u.Object
	if obj == "" {
		obj = "chat.completion"
	}
	return ChatAdaptResult{
		ErrorCategory: CategorySuccess,
		UsageStatus:   st,
		ID:            u.ID,
		Object:        obj,
		Created:       u.Created,
		Model:         model,
		Choices:       choices,
		Usage:         usage,
		FinishReason:  finish,
	}
}

func fail(cat ErrorCategory) ChatAdaptResult {
	return ChatAdaptResult{
		ErrorCategory:   cat,
		UsageStatus:     UsageNotApplicable,
		SuggestedAction: SuggestedActionFor(cat),
	}
}

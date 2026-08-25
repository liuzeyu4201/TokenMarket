package chatcompat

// InspectUsage 判定 usage 完整性。禁止用 {0,0,0} 表示缺失。
func InspectUsage(prompt, completion, total *int, present bool) (UsageStatus, *Usage) {
	if !present {
		return UsageMissing, nil
	}
	if prompt == nil || completion == nil || total == nil {
		return UsageMissing, nil
	}
	p, c, t := *prompt, *completion, *total
	if p < 0 || c < 0 || t < 0 {
		u := &Usage{PromptTokens: prompt, CompletionTokens: completion, TotalTokens: total, Source: "upstream"}
		return UsageInconsistent, u
	}
	if t < p+c {
		u := &Usage{PromptTokens: prompt, CompletionTokens: completion, TotalTokens: total, Source: "upstream"}
		return UsageInconsistent, u
	}
	u := &Usage{PromptTokens: prompt, CompletionTokens: completion, TotalTokens: total, Source: "upstream"}
	return UsageComplete, u
}

// ZeroFilledUsage 是否伪装官方全 0（缺失路径禁止）。
func ZeroFilledUsage(u *Usage, status UsageStatus) bool {
	if status != UsageMissing || u == nil {
		return false
	}
	if u.PromptTokens == nil || u.CompletionTokens == nil || u.TotalTokens == nil {
		return false
	}
	return *u.PromptTokens == 0 && *u.CompletionTokens == 0 && *u.TotalTokens == 0
}

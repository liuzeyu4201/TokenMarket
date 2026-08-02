package providervalid

import "time"

// NewResult 构造结果并强制不变量（quota_unavailable 禁止假 0；rate_limited 必须 retry）。
func NewResult(
	platform string,
	cat ErrorCategory,
	validity Validity,
	availability Availability,
	models []string,
	remaining *string,
	unit *string,
	retryAfter *int,
	credRef string,
	now time.Time,
) CredentialValidationResult {
	if models == nil {
		models = []string{}
	}
	if cat == CategoryQuotaUnavailable {
		remaining = nil
		unit = nil
	}
	if cat == CategoryRateLimited {
		if retryAfter == nil || *retryAfter < 1 {
			v := 5
			retryAfter = &v
		}
	} else {
		// 非限流不强制带 retry；闸门临时失败可带可选值
	}
	if now.IsZero() {
		now = time.Now().UTC()
	} else {
		now = now.UTC()
	}
	return CredentialValidationResult{
		Platform:          platform,
		Validity:          validity,
		Availability:      availability,
		RemainingQuota:    remaining,
		QuotaUnit:         unit,
		SupportedModels:   models,
		CheckedAt:         now,
		ErrorCategory:     cat,
		RetryAfterSeconds: retryAfter,
		CredentialRef:     credRef,
		SuggestedAction:   SuggestedActionFor(cat),
	}
}

// AssertQuotaUnavailableInvariant 测试/调试用：quota_unavailable 时 remaining 不得为 "0"。
func AssertQuotaUnavailableInvariant(r CredentialValidationResult) bool {
	if r.ErrorCategory != CategoryQuotaUnavailable {
		return true
	}
	if r.RemainingQuota == nil {
		return true
	}
	return *r.RemainingQuota != "0" && *r.RemainingQuota != ""
}

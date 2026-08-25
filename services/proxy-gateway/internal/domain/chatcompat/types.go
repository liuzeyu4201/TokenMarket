// Package chatcompat 定义火山方舟 Chat Completions 兼容适配的领域类型（无 I/O）。
package chatcompat

import "encoding/json"

// ErrorCategory 稳定错误分类（volcano-openai-compat/v1）。
type ErrorCategory string

const (
	CategorySuccess              ErrorCategory = "success"
	CategoryInvalid              ErrorCategory = "invalid"
	CategoryForbidden            ErrorCategory = "forbidden"
	CategoryRateLimited          ErrorCategory = "rate_limited"
	CategoryTemporaryUnavailable ErrorCategory = "temporary_unavailable"
	CategoryTimeout              ErrorCategory = "timeout"
	CategoryInvalidResponse      ErrorCategory = "invalid_response"
	CategoryUnsupportedParameter ErrorCategory = "unsupported_parameter"
	CategoryUnsupportedEndpoint  ErrorCategory = "unsupported_endpoint"
	CategoryUnsupportedPlatform  ErrorCategory = "unsupported_platform"
	CategoryTruncatedStream      ErrorCategory = "truncated_stream"
)

// AllErrorCategories 契约全集。
func AllErrorCategories() []ErrorCategory {
	return []ErrorCategory{
		CategorySuccess,
		CategoryInvalid,
		CategoryForbidden,
		CategoryRateLimited,
		CategoryTemporaryUnavailable,
		CategoryTimeout,
		CategoryInvalidResponse,
		CategoryUnsupportedParameter,
		CategoryUnsupportedEndpoint,
		CategoryUnsupportedPlatform,
		CategoryTruncatedStream,
	}
}

// UsageStatus usage 完整性。
type UsageStatus string

const (
	UsageComplete      UsageStatus = "complete"
	UsageMissing       UsageStatus = "missing"
	UsageInconsistent  UsageStatus = "inconsistent"
	UsageNotApplicable UsageStatus = "not_applicable"
)

// StreamKind 流事件种类。
type StreamKind string

const (
	KindDelta     StreamKind = "delta"
	KindDone      StreamKind = "done"
	KindTruncated StreamKind = "truncated"
	KindError     StreamKind = "error"
)

// SuggestedAction 机器可读建议。
type SuggestedAction string

const (
	ActionFixParameter  SuggestedAction = "fix_parameter"
	ActionFixCredential SuggestedAction = "fix_credential"
	ActionRetryLater    SuggestedAction = "retry_later"
	ActionUnsupported   SuggestedAction = "unsupported"
)

// ChatMessage 单条消息；Content 原样 JSON。
type ChatMessage struct {
	Role    string          `json:"role"`
	Content json.RawMessage `json:"content"`
}

// ChatAdaptRequest 同进程适配输入（瞬时）。Raw 若非空则用于检测未声明顶层键。
type ChatAdaptRequest struct {
	Platform         string
	APIKey           string
	RequestID        string
	Endpoint         string
	Model            string
	Messages         []ChatMessage
	Stream           *bool
	Temperature      *float64
	MaxTokens        *int
	TopP             *float64
	Stop             json.RawMessage
	PresencePenalty  *float64
	FrequencyPenalty *float64
	N                *int
	Raw              json.RawMessage
}

// Usage 官方 token 观察。
type Usage struct {
	PromptTokens     *int   `json:"prompt_tokens,omitempty"`
	CompletionTokens *int   `json:"completion_tokens,omitempty"`
	TotalTokens      *int   `json:"total_tokens,omitempty"`
	Source           string `json:"source,omitempty"`
}

// ChatChoice 非流式 choice。
type ChatChoice struct {
	Index        int             `json:"index"`
	FinishReason string          `json:"finish_reason,omitempty"`
	Message      json.RawMessage `json:"message,omitempty"`
}

// ChatAdaptResult 非流式适配结果。
type ChatAdaptResult struct {
	ErrorCategory     ErrorCategory   `json:"error_category"`
	UsageStatus       UsageStatus     `json:"usage_status"`
	ID                string          `json:"id,omitempty"`
	Object            string          `json:"object,omitempty"`
	Created           int64           `json:"created,omitempty"`
	Model             string          `json:"model,omitempty"`
	Choices           []ChatChoice    `json:"choices,omitempty"`
	Usage             *Usage          `json:"usage,omitempty"`
	FinishReason      string          `json:"finish_reason,omitempty"`
	RetryAfterSeconds *int            `json:"retry_after_seconds,omitempty"`
	SuggestedAction   SuggestedAction `json:"suggested_action,omitempty"`
	CredentialRef     string          `json:"credential_ref,omitempty"`
}

// StreamEvent 流式 yield。
type StreamEvent struct {
	Kind              StreamKind      `json:"kind"`
	ID                string          `json:"id,omitempty"`
	Object            string          `json:"object,omitempty"`
	Created           int64           `json:"created,omitempty"`
	Model             string          `json:"model,omitempty"`
	Choices           json.RawMessage `json:"choices,omitempty"`
	Usage             *Usage          `json:"usage,omitempty"`
	ErrorCategory     ErrorCategory   `json:"error_category,omitempty"`
	RetryAfterSeconds *int            `json:"retry_after_seconds,omitempty"`
}

// SuggestedActionFor 按类别给建议。
func SuggestedActionFor(cat ErrorCategory) SuggestedAction {
	switch cat {
	case CategoryInvalid, CategoryForbidden:
		return ActionFixCredential
	case CategoryUnsupportedParameter:
		return ActionFixParameter
	case CategoryUnsupportedEndpoint, CategoryUnsupportedPlatform:
		return ActionUnsupported
	case CategoryRateLimited, CategoryTemporaryUnavailable, CategoryTimeout, CategoryTruncatedStream:
		return ActionRetryLater
	default:
		return ""
	}
}

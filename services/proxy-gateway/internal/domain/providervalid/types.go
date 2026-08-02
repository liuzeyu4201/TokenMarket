// Package providervalid 定义火山方舟（及内部验证）凭证校验领域类型与枚举。
package providervalid

import "time"

// ErrorCategory 稳定错误分类（契约枚举）。
type ErrorCategory string

const (
	CategorySuccess              ErrorCategory = "success"
	CategoryInvalid              ErrorCategory = "invalid"
	CategoryForbidden            ErrorCategory = "forbidden"
	CategoryZeroQuota            ErrorCategory = "zero_quota"
	CategoryQuotaUnavailable     ErrorCategory = "quota_unavailable"
	CategoryNoSupportedModels    ErrorCategory = "no_supported_models"
	CategoryRateLimited          ErrorCategory = "rate_limited"
	CategoryTemporaryUnavailable ErrorCategory = "temporary_unavailable"
	CategoryTimeout              ErrorCategory = "timeout"
	CategoryInvalidResponse      ErrorCategory = "invalid_response"
	CategoryUnsupportedPlatform  ErrorCategory = "unsupported_platform"
)

// AllErrorCategories 契约全集（测试对齐用）。
func AllErrorCategories() []ErrorCategory {
	return []ErrorCategory{
		CategorySuccess,
		CategoryInvalid,
		CategoryForbidden,
		CategoryZeroQuota,
		CategoryQuotaUnavailable,
		CategoryNoSupportedModels,
		CategoryRateLimited,
		CategoryTemporaryUnavailable,
		CategoryTimeout,
		CategoryInvalidResponse,
		CategoryUnsupportedPlatform,
	}
}

// Validity 认证有效性。
type Validity string

const (
	ValidityValid   Validity = "valid"
	ValidityInvalid Validity = "invalid"
	ValidityUnknown Validity = "unknown"
)

// Availability 可路由/可用性。
type Availability string

const (
	AvailabilityAvailable   Availability = "available"
	AvailabilityUnavailable Availability = "unavailable"
)

// SuggestedAction 机器可读建议动作。
type SuggestedAction string

const (
	ActionFixCredential SuggestedAction = "fix_credential"
	ActionAddQuota      SuggestedAction = "add_quota"
	ActionEnableModels  SuggestedAction = "enable_models"
	ActionRetryLater    SuggestedAction = "retry_later"
	ActionUnsupported   SuggestedAction = "unsupported"
	ActionNone          SuggestedAction = "none"
)

// CredentialValidationRequest 单次验证输入（瞬时，不落盘）。
type CredentialValidationRequest struct {
	Platform  string
	APIKey    string
	RequestID string
}

// CredentialValidationResult 单次验证结果值对象。
type CredentialValidationResult struct {
	Platform          string          `json:"platform"`
	Validity          Validity        `json:"validity"`
	Availability      Availability    `json:"availability"`
	RemainingQuota    *string         `json:"remaining_quota"`
	QuotaUnit         *string         `json:"quota_unit"`
	SupportedModels   []string        `json:"supported_models"`
	CheckedAt         time.Time       `json:"checked_at"`
	ErrorCategory     ErrorCategory   `json:"error_category"`
	RetryAfterSeconds *int            `json:"retry_after_seconds,omitempty"`
	CredentialRef     string          `json:"credential_ref,omitempty"`
	SuggestedAction   SuggestedAction `json:"suggested_action,omitempty"`
}

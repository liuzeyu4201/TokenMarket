package httpserver

import (
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

// ValidateDeps 内部验证依赖。
type ValidateDeps struct {
	Enabled   bool
	Token     string
	Validator *application.Validator
}

type validateRequestBody struct {
	Platform  string `json:"platform"`
	APIKey    string `json:"api_key"`
	RequestID string `json:"request_id"`
}

type validateResponseBody struct {
	Platform          string   `json:"platform"`
	Validity          string   `json:"validity"`
	Availability      string   `json:"availability"`
	RemainingQuota    *string  `json:"remaining_quota"`
	QuotaUnit         *string  `json:"quota_unit"`
	SupportedModels   []string `json:"supported_models"`
	CheckedAt         string   `json:"checked_at"`
	ErrorCategory     string   `json:"error_category"`
	RetryAfterSeconds *int     `json:"retry_after_seconds,omitempty"`
	CredentialRef     string   `json:"credential_ref,omitempty"`
	SuggestedAction   string   `json:"suggested_action,omitempty"`
}

func (s *Server) registerInternalValidate(deps ValidateDeps) {
	if !deps.Enabled || deps.Validator == nil {
		return
	}
	s.validateDeps = &deps
	s.engine.POST("/internal/v1/provider-credentials/validate", s.handleValidateCredential)
}

func (s *Server) handleValidateCredential(c *gin.Context) {
	if s.validateDeps == nil || !s.validateDeps.Enabled {
		c.JSON(http.StatusNotFound, gin.H{
			"service":    s.config.Service,
			"status":     "not_found",
			"version":    s.config.Version,
			"request_id": c.GetString("request_id"),
		})
		return
	}
	tok := c.GetHeader("X-Internal-Token")
	if tok == "" || tok != s.validateDeps.Token {
		c.JSON(http.StatusUnauthorized, gin.H{
			"error":      "unauthorized",
			"request_id": c.GetString("request_id"),
		})
		return
	}

	var body validateRequestBody
	if err := c.ShouldBindJSON(&body); err != nil {
		// 非法 JSON：仍尽量返回业务完成语义；使用 invalid_response
		c.JSON(http.StatusOK, validateResponseBody{
			Platform:        "",
			Validity:        string(providervalid.ValidityUnknown),
			Availability:    string(providervalid.AvailabilityUnavailable),
			SupportedModels: []string{},
			CheckedAt:       time.Now().UTC().Format(time.RFC3339),
			ErrorCategory:   string(providervalid.CategoryInvalidResponse),
			SuggestedAction: string(providervalid.ActionRetryLater),
		})
		return
	}

	reqID := strings.TrimSpace(body.RequestID)
	if reqID == "" {
		reqID = c.GetString("request_id")
	}
	// 避免把 token 记入业务日志；api_key 不回显
	_ = reqID

	res := s.validateDeps.Validator.ValidateCredential(c.Request.Context(), providervalid.CredentialValidationRequest{
		Platform:  body.Platform,
		APIKey:    body.APIKey,
		RequestID: reqID,
	})

	// 确保响应绝不包含 api_key 字段
	out := validateResponseBody{
		Platform:          res.Platform,
		Validity:          string(res.Validity),
		Availability:      string(res.Availability),
		RemainingQuota:    res.RemainingQuota,
		QuotaUnit:         res.QuotaUnit,
		SupportedModels:   res.SupportedModels,
		CheckedAt:         res.CheckedAt.UTC().Format(time.RFC3339),
		ErrorCategory:     string(res.ErrorCategory),
		RetryAfterSeconds: res.RetryAfterSeconds,
		CredentialRef:     res.CredentialRef,
		SuggestedAction:   string(res.SuggestedAction),
	}
	if out.SupportedModels == nil {
		out.SupportedModels = []string{}
	}
	c.JSON(http.StatusOK, out)
}

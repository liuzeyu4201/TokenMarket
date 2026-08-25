package httpserver

import (
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func writeEnvelope(c *gin.Context, status int, code, message string) {
	rid := c.GetString("request_id")
	c.Header("X-Request-ID", rid)
	c.JSON(status, gin.H{
		"code":       code,
		"message":    message,
		"data":       nil,
		"request_id": rid,
		"timestamp":  time.Now().UTC().Format(time.RFC3339),
	})
}

func writeEnvelopeRetry(c *gin.Context, status int, code, message string, retryAfter *int) {
	if retryAfter != nil && *retryAfter > 0 {
		c.Header("Retry-After", strconv.Itoa(*retryAfter))
	}
	writeEnvelope(c, status, code, message)
}

func mapUpstream(cat chatcompat.ErrorCategory) (status int, code, message string) {
	switch cat {
	case chatcompat.CategoryUnsupportedParameter, chatcompat.CategoryUnsupportedEndpoint, chatcompat.CategoryUnsupportedPlatform:
		return http.StatusBadRequest, "INVALID_REQUEST", "请求不符合兼容契约"
	case chatcompat.CategoryRateLimited:
		return http.StatusTooManyRequests, "RATE_LIMITED", "上游限流"
	case chatcompat.CategoryTimeout:
		return http.StatusGatewayTimeout, "UPSTREAM_TIMEOUT", "上游超时"
	case chatcompat.CategoryInvalid, chatcompat.CategoryForbidden:
		return http.StatusBadGateway, "UPSTREAM_AUTH", "上游认证或权限失败"
	case chatcompat.CategoryTemporaryUnavailable, chatcompat.CategoryTruncatedStream, chatcompat.CategoryInvalidResponse:
		return http.StatusBadGateway, "UPSTREAM_ERROR", "上游暂时不可用或协议错误"
	default:
		return http.StatusBadGateway, "UPSTREAM_ERROR", "上游调用失败"
	}
}

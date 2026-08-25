package chatcompat

import (
	"bytes"
	"context"
	"errors"
	"net"
	"net/http"
	"strings"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

// ClassifyHTTP 将上游 HTTP 映射为 chat 错误类别（零事件/非流式）。
func ClassifyHTTP(status int, body []byte) ErrorCategory {
	switch status {
	case http.StatusUnauthorized:
		return CategoryInvalid
	case http.StatusForbidden:
		return CategoryForbidden
	case http.StatusTooManyRequests:
		return CategoryRateLimited
	case http.StatusRequestTimeout:
		return CategoryTimeout
	}
	if status >= 500 && status <= 599 {
		return CategoryTemporaryUnavailable
	}
	if status >= 400 && status <= 499 {
		if looksLikeParameterError(body) {
			return CategoryUnsupportedParameter
		}
		return CategoryInvalidResponse
	}
	return CategoryTemporaryUnavailable
}

func looksLikeParameterError(body []byte) bool {
	low := bytes.ToLower(body)
	for _, n := range [][]byte{
		[]byte("invalid_request"),
		[]byte("invalid_param"),
		[]byte("unsupported"),
		[]byte("bad request"),
	} {
		if bytes.Contains(low, n) {
			return true
		}
	}
	return false
}

// ClassifyTransport 网络错误。DeadlineExceeded → timeout；其它连接错误 → temporary。
// context.Canceled 不映射为 timeout（与截止语义分离）；调用方应先检查 Canceled。
func ClassifyTransport(err error) ErrorCategory {
	if err == nil {
		return CategoryTemporaryUnavailable
	}
	if errors.Is(err, context.DeadlineExceeded) {
		return CategoryTimeout
	}
	if errors.Is(err, context.Canceled) {
		return CategoryTimeout // 仅当上层未单独处理 cancel 时的兜底；优先检查 Canceled
	}
	var ne net.Error
	if errors.As(err, &ne) && ne.Timeout() {
		return CategoryTimeout
	}
	msg := strings.ToLower(err.Error())
	if strings.Contains(msg, "timeout") || strings.Contains(msg, "deadline exceeded") {
		return CategoryTimeout
	}
	return CategoryTemporaryUnavailable
}

// IsCallerCancel 是否为调用方取消（非截止）。
func IsCallerCancel(err error) bool {
	return err != nil && errors.Is(err, context.Canceled) && !errors.Is(err, context.DeadlineExceeded)
}

// ParseRetryAfter 复用 SF06 解析器。
func ParseRetryAfter(header string, defaultSec, maxSec int) int {
	return providervalid.ParseRetryAfter(header, defaultSec, maxSec)
}

// ClampDeadline 计算实际截止：缺省 60s，钳制 max。
func ClampDeadline(callerRemaining time.Duration, hasCaller bool, defaultSec, maxSec int) time.Duration {
	if defaultSec < 1 {
		defaultSec = 60
	}
	if maxSec < 1 {
		maxSec = 300
	}
	def := time.Duration(defaultSec) * time.Second
	max := time.Duration(maxSec) * time.Second
	if !hasCaller || callerRemaining <= 0 {
		if def > max {
			return max
		}
		return def
	}
	if callerRemaining > max {
		return max
	}
	return callerRemaining
}

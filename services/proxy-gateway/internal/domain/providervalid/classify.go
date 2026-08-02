package providervalid

import (
	"context"
	"errors"
	"net"
	"net/http"
	"strings"
	"time"
)

// ClassifyHTTPStatus 将上游 HTTP 状态映射为错误类别。
// 200 成功体解析由调用方处理，不在此返回 success。
func ClassifyHTTPStatus(status int) ErrorCategory {
	switch {
	case status == http.StatusUnauthorized:
		return CategoryInvalid
	case status == http.StatusForbidden:
		return CategoryForbidden
	case status == http.StatusTooManyRequests:
		return CategoryRateLimited
	case status == http.StatusRequestTimeout:
		return CategoryTimeout
	case status >= 500 && status <= 599:
		return CategoryTemporaryUnavailable
	case status >= 400 && status <= 499:
		// 其他 4xx 保守为 invalid_response（非明确鉴权）
		return CategoryInvalidResponse
	default:
		return CategoryTemporaryUnavailable
	}
}

// ClassifyTransportError 分类网络/超时错误。
func ClassifyTransportError(err error) ErrorCategory {
	if err == nil {
		return CategoryTemporaryUnavailable
	}
	if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, context.Canceled) {
		return CategoryTimeout
	}
	var ne net.Error
	if errors.As(err, &ne) && ne.Timeout() {
		return CategoryTimeout
	}
	// 常见超时字符串（部分传输栈不暴露 net.Error）
	msg := strings.ToLower(err.Error())
	if strings.Contains(msg, "timeout") || strings.Contains(msg, "deadline exceeded") {
		return CategoryTimeout
	}
	return CategoryTemporaryUnavailable
}

// ParseRetryAfter 解析 Retry-After 头（秒或 HTTP-date），应用默认与钳制。
func ParseRetryAfter(header string, defaultSec, maxSec int) int {
	if defaultSec < 1 {
		defaultSec = 5
	}
	if maxSec < 1 {
		maxSec = 300
	}
	if header == "" {
		return clamp(defaultSec, 1, maxSec)
	}
	// 纯秒
	var sec int
	if _, err := parseASCIIInt(header, &sec); err == nil && sec > 0 {
		return clamp(sec, 1, maxSec)
	}
	// HTTP-date
	if t, err := http.ParseTime(header); err == nil {
		d := int(time.Until(t).Seconds())
		if d < 1 {
			d = 1
		}
		return clamp(d, 1, maxSec)
	}
	return clamp(defaultSec, 1, maxSec)
}

func clamp(v, lo, hi int) int {
	if v < lo {
		return lo
	}
	if v > hi {
		return hi
	}
	return v
}

func parseASCIIInt(s string, out *int) (int, error) {
	s = strings.TrimSpace(s)
	n := 0
	if s == "" {
		return 0, errors.New("empty")
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return 0, errors.New("not int")
		}
		n = n*10 + int(c-'0')
	}
	*out = n
	return n, nil
}

// SuggestedActionFor 根据类别给出建议动作。
func SuggestedActionFor(cat ErrorCategory) SuggestedAction {
	switch cat {
	case CategoryInvalid, CategoryForbidden:
		return ActionFixCredential
	case CategoryZeroQuota:
		return ActionAddQuota
	case CategoryNoSupportedModels:
		return ActionEnableModels
	case CategoryRateLimited, CategoryTemporaryUnavailable, CategoryTimeout, CategoryQuotaUnavailable:
		return ActionRetryLater
	case CategoryUnsupportedPlatform:
		return ActionUnsupported
	case CategorySuccess:
		return ActionNone
	default:
		return ActionRetryLater
	}
}

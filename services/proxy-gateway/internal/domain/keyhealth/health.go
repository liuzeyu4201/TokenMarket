// Package keyhealth SF16 周期健康分类（无调度器 I/O）。
package keyhealth

import "github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"

func MapValidateCategory(cat providervalid.ErrorCategory) (health string, pauseProbe bool) {
	switch cat {
	case providervalid.CategorySuccess:
		return "healthy", false
	case providervalid.CategoryInvalid, providervalid.CategoryForbidden:
		return "invalid", true
	case providervalid.CategoryZeroQuota:
		return "expired", false
	case providervalid.CategoryRateLimited:
		return "rate_limited", true
	case providervalid.CategoryTimeout, providervalid.CategoryTemporaryUnavailable:
		return "down", false
	default:
		return "unknown", false
	}
}

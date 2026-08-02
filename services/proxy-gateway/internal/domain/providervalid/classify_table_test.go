package providervalid_test

import (
	"net/http"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestClassifyTableSC001(t *testing.T) {
	// 表驱动覆盖 SC-001 主要 HTTP 映射
	table := map[int]providervalid.ErrorCategory{
		401: providervalid.CategoryInvalid,
		403: providervalid.CategoryForbidden,
		429: providervalid.CategoryRateLimited,
		500: providervalid.CategoryTemporaryUnavailable,
		503: providervalid.CategoryTemporaryUnavailable,
	}
	for st, want := range table {
		if got := providervalid.ClassifyHTTPStatus(st); got != want {
			t.Fatalf("%d -> %s want %s", st, got, want)
		}
	}
	_ = http.StatusOK
}

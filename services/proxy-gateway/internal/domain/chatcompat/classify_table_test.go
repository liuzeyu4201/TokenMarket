package chatcompat_test

import (
	"net/http"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestClassifyHTTPTable(t *testing.T) {
	cases := []struct {
		status int
		body   string
		want   chatcompat.ErrorCategory
	}{
		{401, "", chatcompat.CategoryInvalid},
		{403, "", chatcompat.CategoryForbidden},
		{429, "", chatcompat.CategoryRateLimited},
		{408, "", chatcompat.CategoryTimeout},
		{500, "", chatcompat.CategoryTemporaryUnavailable},
		{502, "", chatcompat.CategoryTemporaryUnavailable},
		{400, `{"error":{"type":"invalid_request_error"}}`, chatcompat.CategoryUnsupportedParameter},
		{404, `{"error":"nope"}`, chatcompat.CategoryInvalidResponse},
	}
	for _, c := range cases {
		got := chatcompat.ClassifyHTTP(c.status, []byte(c.body))
		if got != c.want {
			t.Errorf("status %d: got %s want %s", c.status, got, c.want)
		}
	}
	_ = http.StatusOK
}

func TestRetryAfterDefaultsAndClamp(t *testing.T) {
	if chatcompat.ParseRetryAfter("", 5, 300) != 5 {
		t.Fatal("default")
	}
	if chatcompat.ParseRetryAfter("12", 5, 300) != 12 {
		t.Fatal("header")
	}
	if chatcompat.ParseRetryAfter("9999", 5, 300) != 300 {
		t.Fatal("clamp")
	}
}

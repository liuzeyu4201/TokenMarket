package providervalid_test

import (
	"context"
	"errors"
	"net/http"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

func TestClassifyHTTPStatus(t *testing.T) {
	cases := []struct {
		status int
		want   providervalid.ErrorCategory
	}{
		{http.StatusUnauthorized, providervalid.CategoryInvalid},
		{http.StatusForbidden, providervalid.CategoryForbidden},
		{http.StatusTooManyRequests, providervalid.CategoryRateLimited},
		{http.StatusRequestTimeout, providervalid.CategoryTimeout},
		{http.StatusInternalServerError, providervalid.CategoryTemporaryUnavailable},
		{http.StatusBadGateway, providervalid.CategoryTemporaryUnavailable},
	}
	for _, tc := range cases {
		if got := providervalid.ClassifyHTTPStatus(tc.status); got != tc.want {
			t.Fatalf("status %d: got %s want %s", tc.status, got, tc.want)
		}
	}
}

func TestClassifyTransportError(t *testing.T) {
	if providervalid.ClassifyTransportError(context.DeadlineExceeded) != providervalid.CategoryTimeout {
		t.Fatal("deadline")
	}
	if providervalid.ClassifyTransportError(context.Canceled) != providervalid.CategoryTimeout {
		t.Fatal("canceled")
	}
	if providervalid.ClassifyTransportError(errors.New("connection reset")) != providervalid.CategoryTemporaryUnavailable {
		t.Fatal("reset")
	}
}

func TestParseRetryAfter(t *testing.T) {
	if got := providervalid.ParseRetryAfter("", 5, 300); got != 5 {
		t.Fatalf("default got %d", got)
	}
	if got := providervalid.ParseRetryAfter("12", 5, 300); got != 12 {
		t.Fatalf("sec got %d", got)
	}
	if got := providervalid.ParseRetryAfter("9999", 5, 300); got != 300 {
		t.Fatalf("clamp got %d", got)
	}
	// HTTP-date ~ 30s future
	h := time.Now().UTC().Add(30 * time.Second).Format(http.TimeFormat)
	got := providervalid.ParseRetryAfter(h, 5, 300)
	if got < 25 || got > 35 {
		t.Fatalf("http-date got %d", got)
	}
}

package httpserver

import (
	"net/http"
	"strings"
)

const maxLoggedHeaderBytes = 256

var headerAllowlist = map[string]struct{}{
	"accept":          {},
	"accept-encoding": {},
	"content-type":    {},
	"content-length":  {},
	"user-agent":      {},
	"x-request-id":    {},
	"host":            {},
}

func headerNameForbidden(lower string) bool {
	for _, needle := range []string{
		"authorization",
		"token",
		"cookie",
		"key",
		"credential",
		"secret",
	} {
		if strings.Contains(lower, needle) {
			return true
		}
	}
	return false
}

// SanitizeHeaders returns an allowlisted, size-capped copy for logs.
// Authorization/token/cookie/key/credential/secret headers are omitted.
func SanitizeHeaders(h http.Header) map[string]string {
	out := make(map[string]string)
	if h == nil {
		return out
	}
	for k, vs := range h {
		lower := strings.ToLower(k)
		if headerNameForbidden(lower) {
			continue
		}
		if _, ok := headerAllowlist[lower]; !ok {
			continue
		}
		v := strings.Join(vs, ",")
		if len(v) > maxLoggedHeaderBytes {
			v = v[:maxLoggedHeaderBytes]
		}
		out[k] = v
	}
	return out
}

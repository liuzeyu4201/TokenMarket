package passthrough

import "net/http"

var inboundDenied = map[string]struct{}{
	"Connection":          {},
	"Keep-Alive":          {},
	"Proxy-Authenticate":  {},
	"Proxy-Authorization": {},
	"Te":                  {},
	"Trailer":             {},
	"Transfer-Encoding":   {},
	"Upgrade":             {},
	"Cookie":              {},
	"Set-Cookie":          {},
	"Authorization":       {},
	"X-Internal-Token":    {},
	"X-Api-Key":           {},
	"X-Forwarded-For":     {},
	"X-Forwarded-Host":    {},
	"X-Forwarded-Proto":   {},
	"X-Real-Ip":           {},
}

var outboundDenied = map[string]struct{}{
	"Set-Cookie":       {},
	"Authorization":    {},
	"X-Api-Key":        {},
	"X-Internal-Token": {},
}

func stripDenied(h http.Header, denied map[string]struct{}) {
	for k := range h {
		if _, ok := denied[http.CanonicalHeaderKey(k)]; ok {
			h.Del(k)
		}
	}
}

func applyUpstreamAuth(h http.Header, protocol, credential string) {
	switch protocol {
	case ProtocolAnthropic:
		h.Set("x-api-key", credential)
	default:
		h.Set("Authorization", "Bearer "+credential)
	}
}

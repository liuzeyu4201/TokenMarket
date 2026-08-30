package passthrough

import (
	"net/http"
	"strings"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

const (
	ProtocolOpenAI       = "openai"
	ProtocolAnthropic    = "anthropic"
	ProtocolVertex       = "vertex"
	CodeUnresolved       = "PROTOCOL_UNRESOLVED"
	CodeNoUpstream       = "NO_UPSTREAM"
	CodeTooLarge         = "REQUEST_TOO_LARGE"
	CodeTimeout          = "UPSTREAM_TIMEOUT"
	CodeCanceled         = "CLIENT_CANCELED"
	CodeAffinityNotFound = "AFFINITY_NOT_FOUND"
	CodeAffinityConflict = "AFFINITY_CONFLICT"
	CodeSlowConsumer     = "SLOW_CONSUMER"
)

func stripProtocolPrefix(path string) (protocol, rest string) {
	p := path
	if p == "" {
		p = "/"
	}
	for _, name := range []string{ProtocolOpenAI, ProtocolAnthropic, ProtocolVertex} {
		pre := "/" + name
		if p == pre {
			return name, "/"
		}
		if strings.HasPrefix(p, pre+"/") {
			return name, p[len(pre):]
		}
	}
	return "", p
}

func hostProtocol(host string) string {
	h := strings.ToLower(host)
	if i := strings.IndexByte(h, ':'); i >= 0 {
		h = h[:i]
	}
	for _, name := range []string{ProtocolOpenAI, ProtocolAnthropic, ProtocolVertex} {
		if h == name || strings.HasPrefix(h, name+".") {
			return name
		}
	}
	return ""
}

func uniqueCatalogProvider(cat *endpcatalog.Catalog, method, path string) string {
	if cat == nil {
		return ""
	}
	var hit string
	for _, p := range []string{ProtocolOpenAI, ProtocolAnthropic, ProtocolVertex} {
		if endpcatalog.Match(cat, p, method, path) == nil {
			continue
		}
		if hit != "" && hit != p {
			return ""
		}
		hit = p
	}
	return hit
}

// Resolve identifies a single native protocol and the catalog path.
func Resolve(r *http.Request, cat *endpcatalog.Catalog) (protocol, path string, errCode string) {
	raw := r.URL.Path
	if pref, rest := stripProtocolPrefix(raw); pref != "" {
		return pref, rest, ""
	}
	if hp := hostProtocol(r.Host); hp != "" {
		return hp, raw, ""
	}
	if u := uniqueCatalogProvider(cat, r.Method, raw); u != "" {
		return u, raw, ""
	}
	if strings.TrimSpace(r.Header.Get("anthropic-version")) != "" {
		return ProtocolAnthropic, raw, ""
	}
	if strings.HasPrefix(raw, "/v1/projects/") || strings.HasPrefix(raw, "/v1beta1/projects/") {
		return ProtocolVertex, raw, ""
	}
	return "", raw, CodeUnresolved
}

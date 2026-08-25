package chatcompat

import "strings"

// ModelMap 公开 ID ↔ 上游 ID。默认恒等。
type ModelMap struct {
	Allowlist []string
	// PublicToUpstream 覆盖；缺省 public==upstream
	PublicToUpstream map[string]string
}

// ResolveOutbound 公开模型 → 上游 ID；未知 → unsupported_parameter。
func (m ModelMap) ResolveOutbound(public string) (upstream string, cat ErrorCategory) {
	public = strings.TrimSpace(public)
	if public == "" {
		return "", CategoryUnsupportedParameter
	}
	if !m.inAllowlist(public) {
		return "", CategoryUnsupportedParameter
	}
	if m.PublicToUpstream != nil {
		if u, ok := m.PublicToUpstream[public]; ok && strings.TrimSpace(u) != "" {
			return strings.TrimSpace(u), ""
		}
	}
	return public, ""
}

// PublicFromUpstream 响应回写公开 ID。
func (m ModelMap) PublicFromUpstream(upstream, requestedPublic string) string {
	requestedPublic = strings.TrimSpace(requestedPublic)
	if requestedPublic != "" && m.inAllowlist(requestedPublic) {
		return requestedPublic
	}
	up := strings.TrimSpace(upstream)
	for pub, u := range m.PublicToUpstream {
		if u == up {
			return pub
		}
	}
	if m.inAllowlist(up) {
		return up
	}
	return requestedPublic
}

func (m ModelMap) inAllowlist(id string) bool {
	for _, a := range m.Allowlist {
		if a == id {
			return true
		}
	}
	return false
}

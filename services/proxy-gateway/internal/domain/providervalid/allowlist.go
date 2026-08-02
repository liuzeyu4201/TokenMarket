package providervalid

import "strings"

// DefaultV01ChatModels 默认种子 allowlist（可被配置覆盖）。
var DefaultV01ChatModels = []string{
	"doubao-pro-32k",
	"doubao-lite-32k",
	"doubao-pro-128k",
}

// ParseAllowlistCSV 解析逗号分隔模型列表；空串表示使用默认。
func ParseAllowlistCSV(csv string) []string {
	csv = strings.TrimSpace(csv)
	if csv == "" {
		out := make([]string, len(DefaultV01ChatModels))
		copy(out, DefaultV01ChatModels)
		return out
	}
	parts := strings.Split(csv, ",")
	var out []string
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

// IntersectModels 返回上游与 allowlist 的交集（顺序按上游出现顺序）。
func IntersectModels(upstream, allowlist []string) []string {
	allow := make(map[string]struct{}, len(allowlist))
	for _, a := range allowlist {
		allow[a] = struct{}{}
	}
	var out []string
	seen := make(map[string]struct{})
	for _, u := range upstream {
		if _, ok := allow[u]; !ok {
			continue
		}
		if _, dup := seen[u]; dup {
			continue
		}
		seen[u] = struct{}{}
		out = append(out, u)
	}
	if out == nil {
		return []string{}
	}
	return out
}

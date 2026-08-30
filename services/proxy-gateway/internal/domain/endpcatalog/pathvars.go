package endpcatalog

import (
	"regexp"
	"sort"
	"strings"
)

var varNamePat = regexp.MustCompile(`\{([^{}/]+)\}`)

// PathVars extracts `{name}` bindings from a matching path template.
func PathVars(tmpl, path string) map[string]string {
	tmpl = normalizePath(tmpl)
	path = normalizePath(path)
	names := varNamePat.FindAllStringSubmatch(tmpl, -1)
	if len(names) == 0 {
		if tmpl == path {
			return map[string]string{}
		}
		return nil
	}
	escaped := regexp.QuoteMeta(tmpl)
	for _, n := range names {
		lit := regexp.QuoteMeta("{" + n[1] + "}")
		escaped = strings.Replace(escaped, lit, `([^/]+)`, 1)
	}
	re := regexp.MustCompile("^" + escaped + "$")
	m := re.FindStringSubmatch(path)
	if m == nil {
		return nil
	}
	out := make(map[string]string, len(names))
	for i, n := range names {
		out[n[1]] = m[i+1]
	}
	return out
}

// ResourceID picks a vendor resource identifier from path variables.
// Preference: `id`, then any `*_id` in name order, then any remaining value.
func ResourceID(vars map[string]string) string {
	if len(vars) == 0 {
		return ""
	}
	if v := strings.TrimSpace(vars["id"]); v != "" {
		return v
	}
	keys := make([]string, 0, len(vars))
	for k := range vars {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		if strings.HasSuffix(k, "_id") {
			if v := strings.TrimSpace(vars[k]); v != "" {
				return v
			}
		}
	}
	for _, k := range keys {
		if v := strings.TrimSpace(vars[k]); v != "" {
			return v
		}
	}
	return ""
}

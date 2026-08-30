package endpcatalog

import (
	"regexp"
	"strings"
	"sync"
)

var (
	varPat    = regexp.MustCompile(`\{[^/]+\}`)
	tmplCache sync.Map // string -> *regexp.Regexp
)

func templateRegexp(tmpl string) *regexp.Regexp {
	if v, ok := tmplCache.Load(tmpl); ok {
		return v.(*regexp.Regexp)
	}
	escaped := regexp.QuoteMeta(tmpl)
	escaped = strings.ReplaceAll(escaped, `\{`, "{")
	escaped = strings.ReplaceAll(escaped, `\}`, "}")
	pattern := "^" + varPat.ReplaceAllString(escaped, `[^/]+`) + "$"
	re := regexp.MustCompile(pattern)
	tmplCache.Store(tmpl, re)
	return re
}

func normalizePath(p string) string {
	if i := strings.IndexByte(p, '?'); i >= 0 {
		p = p[:i]
	}
	if p == "" {
		return "/"
	}
	if !strings.HasPrefix(p, "/") {
		p = "/" + p
	}
	if len(p) > 1 && strings.HasSuffix(p, "/") {
		p = strings.TrimRight(p, "/")
	}
	return p
}

func Match(c *Catalog, provider, method, path string) *EndpointRecord {
	if c == nil {
		return nil
	}
	method = strings.ToUpper(method)
	path = normalizePath(path)
	var best *EndpointRecord
	bestVars := 1 << 30
	bestLit := -1
	bestLen := -1
	for i := range c.Records {
		rec := &c.Records[i]
		if rec.Provider != provider || rec.Method != method {
			continue
		}
		if !templateRegexp(rec.PathTemplate).MatchString(path) {
			continue
		}
		vars := len(varNamePat.FindAllString(rec.PathTemplate, -1))
		lit := len(varNamePat.ReplaceAllString(rec.PathTemplate, ""))
		n := len(rec.PathTemplate)
		if vars < bestVars || (vars == bestVars && lit > bestLit) || (vars == bestVars && lit == bestLit && n > bestLen) {
			best = rec
			bestVars = vars
			bestLit = lit
			bestLen = n
		}
	}
	return best
}

func Admit(c *Catalog, in AdmitInput) Decision {
	rec := Match(c, in.Provider, in.Method, in.Path)
	if rec == nil {
		return Decision{Allow: false, Code: CodeNotCataloged}
	}
	if rec.Stability == "control_plane" {
		return Decision{Allow: false, Code: CodeControlPlane, Record: rec}
	}
	if rec.Stability == "preview" || rec.Stability == "beta" {
		if !in.PreviewOptIn {
			return Decision{Allow: false, Code: CodePreview, Record: rec}
		}
	}
	mode := in.ProjectMode
	if mode == "" {
		mode = "unknown"
	}
	needsDedicated := rec.Stateful || rec.Affinity == "resource_id" || rec.Affinity == "connection"
	if needsDedicated && mode != "dedicated" {
		return Decision{Allow: false, Code: CodeDedicatedRequired, Record: rec}
	}
	return Decision{Allow: true, Record: rec}
}

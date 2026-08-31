package observability

import (
	"sort"
	"strings"
	"sync"
	"time"
)

var allowedLabels = map[string]struct{}{
	"protocol": {},
	"endpoint": {},
	"status":   {},
	"plane":    {},
	"stream":   {},
	"result":   {},
	"reason":   {},
	"state":    {},
}

var forbiddenLabels = map[string]struct{}{
	"user_id":    {},
	"project_id": {},
	"request_id": {},
	"account_id": {},
	"api_key":    {},
}

var secretMarkers = []string{
	"sk-", "api_key", "apikey", "password", "otp", "begin private", "plaintext",
}

// Hop is one stage in a request-correlated trace.
type Hop struct {
	RequestID string
	Service   string
	Stage     string
	Kind      string
	Freshness string
	At        time.Time
}

// TraceLog stores hops for correlate-by-request-id.
type TraceLog struct {
	mu   sync.Mutex
	hops []Hop
}

func NewTraceLog() *TraceLog {
	return &TraceLog{}
}

func (l *TraceLog) Append(h Hop) {
	if l == nil {
		return
	}
	l.mu.Lock()
	l.hops = append(l.hops, h)
	l.mu.Unlock()
}

func (l *TraceLog) Correlate(requestID string) []Hop {
	if l == nil {
		return nil
	}
	order := []string{"proxy", "route", "upstream", "usage", "ledger"}
	l.mu.Lock()
	defer l.mu.Unlock()
	byStage := map[string]Hop{}
	for _, h := range l.hops {
		if h.RequestID == requestID {
			byStage[h.Stage] = h
		}
	}
	out := make([]Hop, 0, len(order))
	for _, stage := range order {
		if h, ok := byStage[stage]; ok {
			out = append(out, h)
		}
	}
	return out
}

func AllowLabels(labels map[string]string) bool {
	for key := range labels {
		if _, bad := forbiddenLabels[key]; bad {
			return false
		}
		if _, ok := allowedLabels[key]; !ok {
			return false
		}
	}
	return true
}

// LabelGuard caps unique label combinations.
type LabelGuard struct {
	max  int
	mu   sync.Mutex
	seen map[string]struct{}
}

func NewLabelGuard(max int) *LabelGuard {
	return &LabelGuard{max: max, seen: map[string]struct{}{}}
}

func (g *LabelGuard) Allow(labels map[string]string) bool {
	if !AllowLabels(labels) {
		return false
	}
	keys := make([]string, 0, len(labels))
	for k, v := range labels {
		keys = append(keys, k+"="+v)
	}
	sort.Strings(keys)
	sig := strings.Join(keys, ",")
	g.mu.Lock()
	defer g.mu.Unlock()
	if _, ok := g.seen[sig]; ok {
		return true
	}
	if len(g.seen) >= g.max {
		return false
	}
	g.seen[sig] = struct{}{}
	return true
}

func ScanSecrets(blob string) []string {
	lowered := strings.ToLower(blob)
	var hits []string
	for _, m := range secretMarkers {
		if strings.Contains(lowered, m) {
			hits = append(hits, m)
		}
	}
	return hits
}

func Redact(blob string) string {
	out := blob
	for _, m := range ScanSecrets(blob) {
		out = strings.ReplaceAll(out, m, "[redacted]")
		out = strings.ReplaceAll(out, strings.ToUpper(m), "[redacted]")
	}
	return out
}

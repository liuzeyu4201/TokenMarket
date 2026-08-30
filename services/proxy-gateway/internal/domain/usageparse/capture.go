// Package usageparse extracts verifiable spend and multi-dimension usage
// from native vendor JSON/SSE without filling missing values as 0.
package usageparse

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math/big"
	"strconv"
	"strings"
)

const ParserVersion = "1.0.0"

const (
	StatusReported   = "reported"
	StatusRated      = "rated"
	StatusUnresolved = "unresolved"
	StatusNone       = "none"
)

// Capture is the standardized observation after parsing one upstream body.
type Capture struct {
	RequestID        string     `json:"request_id,omitempty"`
	ProjectID        string     `json:"project_id,omitempty"`
	Provider         string     `json:"provider"`
	EndpointID       string     `json:"endpoint_id,omitempty"`
	MeteringSource   string     `json:"metering_source,omitempty"`
	CostStatus       string     `json:"cost_status"`
	SettlementBasis  string     `json:"settlement_basis"`
	ReportedMinor    *int64     `json:"reported_cost_minor_units"`
	Currency         string     `json:"currency,omitempty"`
	CostScale        int        `json:"cost_scale"`
	Usage            Dimensions `json:"usage"`
	DualPresent      bool       `json:"dual_present"`
	ParserVersion    string     `json:"parser_version"`
	EvidenceDigest   string     `json:"evidence_digest"`
	UnresolvedReason string     `json:"unresolved_reason,omitempty"`
	Integrity        string     `json:"integrity"`
}

// Dimensions are optional integer counts. A nil pointer means missing, never unknown-zero.
type Dimensions struct {
	InputTokens      *int64 `json:"input_tokens"`
	OutputTokens     *int64 `json:"output_tokens"`
	TotalTokens      *int64 `json:"total_tokens"`
	CacheReadTokens  *int64 `json:"cache_read_tokens"`
	CacheWriteTokens *int64 `json:"cache_write_tokens"`
	ReasoningTokens  *int64 `json:"reasoning_tokens"`
	ImageUnits       *int64 `json:"image_units"`
	AudioMS          *int64 `json:"audio_ms"`
	DurationMS       *int64 `json:"duration_ms"`
}

func (d Dimensions) any() bool {
	return d.InputTokens != nil || d.OutputTokens != nil || d.TotalTokens != nil ||
		d.CacheReadTokens != nil || d.CacheWriteTokens != nil || d.ReasoningTokens != nil ||
		d.ImageUnits != nil || d.AudioMS != nil || d.DurationMS != nil
}

func (d Dimensions) invalid() bool {
	for _, p := range []*int64{d.InputTokens, d.OutputTokens, d.TotalTokens, d.CacheReadTokens, d.CacheWriteTokens, d.ReasoningTokens, d.ImageUnits, d.AudioMS, d.DurationMS} {
		if p != nil && *p < 0 {
			return true
		}
	}
	return false
}

// ParseBody interprets a complete JSON object or an SSE byte stream.
func ParseBody(provider, metering, body string, sse bool) Capture {
	c := Capture{
		Provider:       provider,
		MeteringSource: metering,
		ParserVersion:  ParserVersion,
		CostScale:      6,
		Integrity:      "complete",
	}
	var err error
	if sse {
		err = harvestSSE(&c, provider, body)
	} else {
		err = harvestJSON(&c, provider, []byte(strings.TrimSpace(body)))
	}
	if err != nil {
		c.CostStatus = StatusUnresolved
		c.SettlementBasis = StatusUnresolved
		c.UnresolvedReason = err.Error()
		c.Integrity = "failed"
		c.ReportedMinor = nil
		c.EvidenceDigest = digest(c)
		return c
	}
	if c.Usage.invalid() {
		c.UnresolvedReason = "negative_usage"
	}
	applyStrategy(&c)
	switch c.UnresolvedReason {
	case "negative_usage", "negative_cost", "overflow", "unknown_unit", "parse_failed":
		c.CostStatus = StatusUnresolved
		c.SettlementBasis = StatusUnresolved
		c.Integrity = "failed"
		c.ReportedMinor = nil
	}
	c.EvidenceDigest = digest(c)
	return c
}

func applyStrategy(c *Capture) {
	hasCost := c.ReportedMinor != nil
	hasUsage := c.Usage.any()
	c.DualPresent = hasCost && hasUsage
	switch c.MeteringSource {
	case "none":
		c.CostStatus = StatusNone
		c.SettlementBasis = StatusNone
		c.ReportedMinor = nil
		return
	case "unresolved":
		c.CostStatus = StatusUnresolved
		c.SettlementBasis = StatusUnresolved
		if c.UnresolvedReason == "" {
			c.UnresolvedReason = "catalog_unresolved"
		}
		return
	case "reported_cost":
		if hasCost {
			c.CostStatus = StatusReported
			c.SettlementBasis = StatusReported
			return
		}
		c.CostStatus = StatusUnresolved
		c.SettlementBasis = StatusUnresolved
		c.UnresolvedReason = "missing_cost"
		return
	case "usage":
		if hasUsage {
			c.CostStatus = StatusRated
			c.SettlementBasis = "usage"
			return
		}
		c.CostStatus = StatusUnresolved
		c.SettlementBasis = StatusUnresolved
		c.UnresolvedReason = "missing_usage"
		return
	default: // mixed or empty treated as mixed
		if hasCost {
			c.CostStatus = StatusReported
			c.SettlementBasis = StatusReported
			return
		}
		if hasUsage {
			c.CostStatus = StatusRated
			c.SettlementBasis = "usage"
			return
		}
		c.CostStatus = StatusUnresolved
		c.SettlementBasis = StatusUnresolved
		c.UnresolvedReason = "missing_cost_and_usage"
	}
}

func harvestJSON(c *Capture, provider string, raw []byte) error {
	if len(raw) == 0 {
		return nil
	}
	var top map[string]any
	dec := json.NewDecoder(strings.NewReader(string(raw)))
	dec.UseNumber()
	if err := dec.Decode(&top); err != nil {
		return fmt.Errorf("parse_failed")
	}
	return extractMap(c, provider, top)
}

func extractMap(c *Capture, provider string, top map[string]any) error {
	switch provider {
	case "anthropic":
		extractAnthropic(c, top)
	case "vertex":
		extractVertex(c, top)
	default:
		extractOpenAI(c, top)
	}
	return nil
}

func extractOpenAI(c *Capture, top map[string]any) {
	if u, ok := asMap(top["usage"]); ok {
		setInt(&c.Usage.InputTokens, u["prompt_tokens"])
		setInt(&c.Usage.OutputTokens, u["completion_tokens"])
		setInt(&c.Usage.TotalTokens, u["total_tokens"])
		if d, ok := asMap(u["prompt_tokens_details"]); ok {
			setInt(&c.Usage.CacheReadTokens, first(d, "cached_tokens", "cache_read_tokens"))
		}
		if d, ok := asMap(u["completion_tokens_details"]); ok {
			setInt(&c.Usage.ReasoningTokens, first(d, "reasoning_tokens"))
		}
		tryCost(c, u["cost"])
		tryCost(c, u["total_cost"])
	}
	tryCost(c, top["cost"])
	tryCost(c, top["total_cost"])
}

func extractAnthropic(c *Capture, top map[string]any) {
	u, ok := asMap(top["usage"])
	if !ok {
		if msg, mok := asMap(top["message"]); mok {
			u, ok = asMap(msg["usage"])
		}
	}
	if !ok {
		return
	}
	setInt(&c.Usage.InputTokens, u["input_tokens"])
	setInt(&c.Usage.OutputTokens, u["output_tokens"])
	setInt(&c.Usage.CacheReadTokens, first(u, "cache_read_input_tokens"))
	setInt(&c.Usage.CacheWriteTokens, first(u, "cache_creation_input_tokens", "cache_creation_tokens"))
}

func extractVertex(c *Capture, top map[string]any) {
	u, ok := asMap(top["usageMetadata"])
	if !ok {
		u, ok = asMap(top["usage_metadata"])
	}
	if !ok {
		return
	}
	setInt(&c.Usage.InputTokens, first(u, "promptTokenCount", "prompt_token_count"))
	setInt(&c.Usage.OutputTokens, first(u, "candidatesTokenCount", "candidates_token_count"))
	setInt(&c.Usage.TotalTokens, first(u, "totalTokenCount", "total_token_count"))
	setInt(&c.Usage.ReasoningTokens, first(u, "thoughtsTokenCount", "thoughts_token_count"))
	setInt(&c.Usage.CacheReadTokens, first(u, "cachedContentTokenCount"))
}

func harvestSSE(c *Capture, provider, body string) error {
	c.Integrity = "partial"
	blocks := strings.Split(body, "\n\n")
	var lastErr error
	seen := false
	for _, b := range blocks {
		var data []string
		for _, line := range strings.Split(b, "\n") {
			line = strings.TrimSpace(line)
			if strings.HasPrefix(line, "data:") {
				data = append(data, strings.TrimSpace(strings.TrimPrefix(line, "data:")))
			}
		}
		payload := strings.Join(data, "")
		if payload == "" || payload == "[DONE]" {
			continue
		}
		var top map[string]any
		dec := json.NewDecoder(strings.NewReader(payload))
		dec.UseNumber()
		if err := dec.Decode(&top); err != nil {
			lastErr = fmt.Errorf("parse_failed")
			continue
		}
		seen = true
		_ = extractMap(c, provider, top)
		if inner, ok := asMap(top["delta"]); ok {
			if u, ok := asMap(inner["usage"]); ok {
				tmp := map[string]any{"usage": u}
				_ = extractMap(c, provider, tmp)
			}
		}
	}
	if c.Usage.any() || c.ReportedMinor != nil {
		if c.Usage.any() && (c.Usage.InputTokens != nil || c.Usage.OutputTokens != nil) {
			c.Integrity = "complete"
		}
		return nil
	}
	if lastErr != nil && !seen {
		return lastErr
	}
	return nil
}

func tryCost(c *Capture, v any) {
	if c.ReportedMinor != nil || v == nil {
		return
	}
	s, ok := stringifyNumber(v)
	if !ok {
		if m, ok := asMap(v); ok {
			if cur, _ := m["currency"].(string); cur != "" {
				c.Currency = strings.ToUpper(cur)
			}
			s, ok = stringifyNumber(first(m, "amount", "value", "total"))
			if !ok {
				return
			}
		} else {
			return
		}
	}
	minor, err := toMicro(s)
	if err != nil {
		c.UnresolvedReason = err.Error()
		return
	}
	c.ReportedMinor = &minor
	if c.Currency == "" {
		c.Currency = "USD"
	}
}

func stringifyNumber(v any) (string, bool) {
	switch t := v.(type) {
	case json.Number:
		return t.String(), true
	case string:
		if strings.TrimSpace(t) == "" {
			return "", false
		}
		return t, true
	case float64:
		return strconv.FormatFloat(t, 'f', -1, 64), true
	default:
		return "", false
	}
}

func toMicro(s string) (int64, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0, fmt.Errorf("unknown_unit")
	}
	if strings.ContainsAny(s, "eE") {
		return 0, fmt.Errorf("unknown_unit")
	}
	r := new(big.Rat)
	if _, ok := r.SetString(s); !ok {
		return 0, fmt.Errorf("parse_failed")
	}
	if r.Sign() < 0 {
		return 0, fmt.Errorf("negative_cost")
	}
	scale := new(big.Rat).SetInt(new(big.Int).Exp(big.NewInt(10), big.NewInt(6), nil))
	r.Mul(r, scale)
	if !r.IsInt() {
		// truncating leftover below micro is overflow/unknown precision
		num := new(big.Int).Quo(r.Num(), r.Denom())
		if !num.IsInt64() {
			return 0, fmt.Errorf("overflow")
		}
		return num.Int64(), nil
	}
	n := r.Num()
	if !n.IsInt64() {
		return 0, fmt.Errorf("overflow")
	}
	return n.Int64(), nil
}

func setInt(dst **int64, v any) {
	if v == nil {
		return
	}
	s, ok := stringifyNumber(v)
	if !ok {
		return
	}
	if strings.ContainsAny(s, ".eE") {
		return
	}
	n := new(big.Int)
	if _, ok := n.SetString(s, 10); !ok {
		return
	}
	if !n.IsInt64() {
		neg := int64(-1)
		*dst = &neg
		return
	}
	val := n.Int64()
	*dst = &val
}

func asMap(v any) (map[string]any, bool) {
	m, ok := v.(map[string]any)
	return m, ok
}

func first(m map[string]any, keys ...string) any {
	for _, k := range keys {
		if v, ok := m[k]; ok && v != nil {
			return v
		}
	}
	return nil
}

func digest(c Capture) string {
	type slim struct {
		P   string `json:"p"`
		PV  string `json:"pv"`
		CS  string `json:"cs"`
		SB  string `json:"sb"`
		R   *int64 `json:"r"`
		In  *int64 `json:"in"`
		Out *int64 `json:"out"`
		Tot *int64 `json:"tot"`
		CR  *int64 `json:"cr"`
		CW  *int64 `json:"cw"`
		Re  *int64 `json:"re"`
	}
	b, _ := json.Marshal(slim{
		P: c.Provider, PV: ParserVersion, CS: c.CostStatus, SB: c.SettlementBasis, R: c.ReportedMinor,
		In: c.Usage.InputTokens, Out: c.Usage.OutputTokens, Tot: c.Usage.TotalTokens,
		CR: c.Usage.CacheReadTokens, CW: c.Usage.CacheWriteTokens, Re: c.Usage.ReasoningTokens,
	})
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}

// Forbidden reports whether a JSON encoding leaked banned keys.
func Forbidden(raw []byte) bool {
	s := strings.ToLower(string(raw))
	for _, k := range []string{"raw_body", "api_key", "authorization", "credential"} {
		if strings.Contains(s, `"`+k+`"`) {
			return true
		}
	}
	return false
}

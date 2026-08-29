package chatcompat

import (
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config chat 适配配置。
type Config struct {
	BaseURL            string
	Allowlist          []string
	ModelMap           map[string]string
	DefaultDeadlineSec int
	MaxDeadlineSec     int
	MaxBodyBytes       int
	MaxResponseBytes   int
	DefaultRetryAfter  int
	MaxRetryAfter      int
	HMACSecret         string
}

// LoadConfigFromEnv 从环境加载。空 allowlist fail-closed。
func LoadConfigFromEnv() (Config, error) {
	base := firstNonEmpty(os.Getenv("VOLCANO_CHAT_BASE_URL"), os.Getenv("VOLCANO_VALIDATE_BASE_URL"),
		"https://ark.cn-beijing.volces.com/api/v3")
	allow := parseCSV(os.Getenv("VOLCANO_V01_CHAT_MODELS"))
	if len(allow) == 0 {
		allow = []string{"doubao-pro-32k", "doubao-lite-32k", "doubao-pro-128k"}
	}
	cfg := Config{
		BaseURL:            strings.TrimRight(base, "/"),
		Allowlist:          allow,
		ModelMap:           parseModelMap(os.Getenv("VOLCANO_CHAT_MODEL_MAP")),
		DefaultDeadlineSec: envInt("VOLCANO_CHAT_DEFAULT_DEADLINE_SECONDS", 60),
		MaxDeadlineSec:     envInt("VOLCANO_CHAT_MAX_DEADLINE_SECONDS", 300),
		MaxBodyBytes:       envInt("VOLCANO_CHAT_MAX_BODY_BYTES", 2097152),
		MaxResponseBytes:   envInt("VOLCANO_CHAT_MAX_RESPONSE_BYTES", 2097152),
		DefaultRetryAfter:  envInt("VOLCANO_VALIDATE_DEFAULT_RETRY_AFTER_SECONDS", 5),
		MaxRetryAfter:      envInt("VOLCANO_VALIDATE_MAX_RETRY_AFTER_SECONDS", 300),
		HMACSecret:         firstNonEmpty(os.Getenv("VOLCANO_VALIDATE_GATE_HMAC_SECRET"), "providervalid-dev-only-gate-secret"),
	}
	if err := cfg.Validate(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

// Validate fail-closed。
func (c Config) Validate() error {
	if len(c.Allowlist) == 0 {
		return fmt.Errorf("chatcompat: empty model allowlist")
	}
	if c.DefaultDeadlineSec < 1 {
		return fmt.Errorf("chatcompat: default deadline must be >= 1")
	}
	if c.MaxBodyBytes < 1 {
		return fmt.Errorf("chatcompat: max body bytes must be >= 1")
	}
	if c.MaxResponseBytes < 0 {
		return fmt.Errorf("chatcompat: max response bytes must be >= 0")
	}
	return nil
}

func parseCSV(s string) []string {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

func parseModelMap(s string) map[string]string {
	s = strings.TrimSpace(s)
	if s == "" {
		return nil
	}
	m := map[string]string{}
	for _, part := range strings.Split(s, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		kv := strings.SplitN(part, "=", 2)
		if len(kv) != 2 {
			continue
		}
		k, v := strings.TrimSpace(kv[0]), strings.TrimSpace(kv[1])
		if k != "" && v != "" {
			m[k] = v
		}
	}
	return m
}

func envInt(k string, def int) int {
	s := strings.TrimSpace(os.Getenv(k))
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return def
	}
	return n
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if strings.TrimSpace(v) != "" {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

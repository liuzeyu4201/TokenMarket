package providervalid

import (
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
)

// Config 验证与内部 HTTP 配置。
type Config struct {
	AppEnv string

	// 上游
	BaseURL            string
	Allowlist          []string
	DefaultRetryAfter  int
	MaxRetryAfter      int
	GateHMACSecret     string
	GlobalConcurrency  int
	PerCredConcurrency int

	// 内部路由
	InternalEnabled  bool
	InternalToken    string
	InternalBind     string // 内部验证监听主机，默认 127.0.0.1
	InternalPort     string // 非 local 隔离监听端口；空则用 PORT
	AllowNonLoopback bool
}

// IsLocalAppEnv 是否 local/dev（允许将内部验证挂到公网同进程 listener 仅用于开发）。
func IsLocalAppEnv(appEnv string) bool {
	env := strings.ToLower(strings.TrimSpace(appEnv))
	return env == "local" || env == "dev" || env == ""
}

// PublicListenAddr 公网/主监听地址（健康检查等）。始终 :port 形式。
func PublicListenAddr(port string) string {
	if strings.TrimSpace(port) == "" {
		port = "8080"
	}
	return ":" + strings.TrimPrefix(port, ":")
}

// InternalListenAddr 内部验证监听地址（C1：非 local 必须回环 host）。
// host 来自 InternalBind；port 优先 InternalPort，否则 publicPort。
func InternalListenAddr(bindHost, internalPort, publicPort string) string {
	host := strings.TrimSpace(bindHost)
	if host == "" {
		host = "127.0.0.1"
	}
	port := strings.TrimSpace(internalPort)
	if port == "" {
		port = strings.TrimSpace(publicPort)
	}
	if port == "" {
		port = "8080"
	}
	port = strings.TrimPrefix(port, ":")
	// 若 bind 已是 host:port，原样返回（仅 host 部分校验在 Validate）
	if _, _, err := net.SplitHostPort(host); err == nil {
		return host
	}
	return net.JoinHostPort(host, port)
}

// LoadConfigFromEnv 从环境变量加载。
func LoadConfigFromEnv() (Config, error) {
	cfg := Config{
		AppEnv:             firstNonEmpty(os.Getenv("APP_ENV"), os.Getenv("MODE"), "local"),
		BaseURL:            firstNonEmpty(os.Getenv("VOLCANO_VALIDATE_BASE_URL"), "https://ark.cn-beijing.volces.com/api/v3"),
		Allowlist:          ParseAllowlistCSV(os.Getenv("VOLCANO_V01_CHAT_MODELS")),
		DefaultRetryAfter:  envInt("VOLCANO_VALIDATE_DEFAULT_RETRY_AFTER_SECONDS", 5),
		MaxRetryAfter:      envInt("VOLCANO_VALIDATE_MAX_RETRY_AFTER_SECONDS", 300),
		GateHMACSecret:     firstNonEmpty(os.Getenv("VOLCANO_VALIDATE_GATE_HMAC_SECRET"), "providervalid-dev-only-gate-secret"),
		GlobalConcurrency:  envInt("VOLCANO_VALIDATE_GLOBAL_CONCURRENCY", 32),
		PerCredConcurrency: envInt("VOLCANO_VALIDATE_PER_CREDENTIAL_CONCURRENCY", 1),
		InternalEnabled:    envBool("PROVIDER_VALIDATE_INTERNAL_ENABLED", false),
		InternalToken:      os.Getenv("PROVIDER_VALIDATE_INTERNAL_TOKEN"),
		InternalBind:       firstNonEmpty(os.Getenv("PROVIDER_VALIDATE_BIND"), "127.0.0.1"),
		InternalPort:       strings.TrimSpace(os.Getenv("PROVIDER_VALIDATE_INTERNAL_PORT")),
		AllowNonLoopback:   envBool("PROVIDER_VALIDATE_ALLOW_NON_LOOPBACK", false),
	}
	return cfg, cfg.Validate()
}

// Validate 校验配置（含 C1 fail-closed）。
func (c Config) Validate() error {
	if len(c.Allowlist) == 0 {
		return fmt.Errorf("VOLCANO_V01_CHAT_MODELS allowlist must not be empty")
	}
	if c.GlobalConcurrency < 1 {
		return fmt.Errorf("global concurrency must be >= 1")
	}
	if c.PerCredConcurrency < 1 {
		return fmt.Errorf("per-credential concurrency must be >= 1")
	}
	if c.DefaultRetryAfter < 1 {
		return fmt.Errorf("default retry after must be >= 1")
	}
	if c.MaxRetryAfter < 1 {
		return fmt.Errorf("max retry after must be >= 1")
	}
	if !c.InternalEnabled {
		return nil
	}
	if strings.TrimSpace(c.InternalToken) == "" {
		return fmt.Errorf("PROVIDER_VALIDATE_INTERNAL_TOKEN required when internal validate enabled")
	}
	// C1: 非 local 启用时必须回环或显式允许非回环（运维私网例外）
	if IsLocalAppEnv(c.AppEnv) {
		return nil
	}
	if c.AllowNonLoopback {
		return nil
	}
	if !isLoopbackHost(c.InternalBind) {
		return fmt.Errorf("C1 fail-closed: APP_ENV=%s with internal validate enabled requires loopback bind (got %q) or PROVIDER_VALIDATE_ALLOW_NON_LOOPBACK=true on private network only", c.AppEnv, c.InternalBind)
	}
	return nil
}

// MustIsolateInternalListener 非 local 且启用内部验证时，必须使用独立回环 listener（不得挂在公网 :port 上）。
func (c Config) MustIsolateInternalListener() bool {
	return c.InternalEnabled && !IsLocalAppEnv(c.AppEnv)
}

func isLoopbackHost(host string) bool {
	host = strings.TrimSpace(host)
	if host == "" || host == "127.0.0.1" || host == "::1" || host == "localhost" {
		return true
	}
	// host:port
	if h, _, err := net.SplitHostPort(host); err == nil {
		host = h
	}
	ip := net.ParseIP(host)
	if ip != nil {
		return ip.IsLoopback()
	}
	return strings.EqualFold(host, "localhost")
}

func envInt(key string, def int) int {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return def
	}
	return n
}

func envBool(key string, def bool) bool {
	v := strings.TrimSpace(strings.ToLower(os.Getenv(key)))
	if v == "" {
		return def
	}
	return v == "1" || v == "true" || v == "yes" || v == "on"
}

func firstNonEmpty(vals ...string) string {
	for _, v := range vals {
		if strings.TrimSpace(v) != "" {
			return strings.TrimSpace(v)
		}
	}
	return ""
}

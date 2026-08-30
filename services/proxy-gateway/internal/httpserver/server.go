// Package httpserver provides the SF01 operational HTTP surface for the proxy
// gateway (liveness/readiness/metrics) plus optional internal credential validation.
package httpserver

import (
	"crypto/rand"
	"fmt"
	"log/slog"
	"net/http"
	"sync/atomic"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Config holds server construction parameters.
type Config struct {
	Service string
	Version string
	Logger  *slog.Logger
	// Validate 可选：内部凭证验证（默认 nil = 不挂载）
	Validate *ValidateDeps
	// MountValidate 为 true 时才在本 Server 上挂载 validate 路由（C1：公网 listener 可关掉）
	MountValidate bool
	Proxy         *ProxyDeps
	// CatalogReady 非 nil 且为 false 时 readiness 失败关闭（目录未锁定）。
	CatalogReady *bool
}

// Server wraps the Gin engine and configuration.
type Server struct {
	config         Config
	engine         *gin.Engine
	validateDeps   *ValidateDeps
	proxyEnabled   bool
	metricsHandler http.Handler
	metricsReg     prometheus.Registerer
	registerCount  atomic.Int32
}

// NewServer creates an operational scaffold server (health/metrics + optional validate).
func NewServer(cfg Config) (*Server, error) {
	if cfg.Logger == nil {
		cfg.Logger = slog.Default()
	}
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(requestIDMiddleware(cfg.Logger))
	r.Use(gin.Recovery())

	s := &Server{config: cfg, engine: r}
	s.initMetrics()
	r.GET("/health/live", s.liveness)
	r.GET("/health/ready", s.readiness)
	r.GET("/metrics", s.metrics)
	if cfg.MountValidate && cfg.Validate != nil && cfg.Validate.Enabled {
		s.registerInternalValidate(*cfg.Validate)
	}
	if cfg.Proxy != nil && cfg.Proxy.Enabled {
		s.proxyEnabled = true
		s.registerProxy(*cfg.Proxy)
	}
	r.NoRoute(s.notFound)
	return s, nil
}

// NewInternalValidateServer 仅挂载内部验证路由（+ liveness），用于回环隔离 listener（C1）。
func NewInternalValidateServer(cfg Config) (*Server, error) {
	if cfg.Logger == nil {
		cfg.Logger = slog.Default()
	}
	if cfg.Validate == nil || !cfg.Validate.Enabled {
		return nil, fmt.Errorf("internal validate server requires enabled Validate deps")
	}
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(requestIDMiddleware(cfg.Logger))
	r.Use(gin.Recovery())

	s := &Server{config: cfg, engine: r}
	r.GET("/health/live", s.liveness)
	s.registerInternalValidate(*cfg.Validate)
	r.NoRoute(s.notFound)
	return s, nil
}

// HasValidateRoute 是否已挂载内部验证（测试/断言用）。
func (s *Server) HasValidateRoute() bool {
	return s != nil && s.validateDeps != nil && s.validateDeps.Enabled
}

// HasProxyRoute 是否已挂载公开 Chat Completions 代理。
func (s *Server) HasProxyRoute() bool {
	return s != nil && s.proxyEnabled
}

// Handler returns the HTTP handler for tests.
func (s *Server) Handler() http.Handler {
	return s.engine
}

func (s *Server) healthResponse(c *gin.Context, status string) {
	c.JSON(http.StatusOK, gin.H{
		"service":    s.config.Service,
		"status":     status,
		"version":    s.config.Version,
		"request_id": c.GetString("request_id"),
	})
}

func (s *Server) liveness(c *gin.Context) {
	s.healthResponse(c, "alive")
}

func (s *Server) readiness(c *gin.Context) {
	if s.config.CatalogReady != nil && !*s.config.CatalogReady {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"service":    s.config.Service,
			"status":     "not_ready",
			"version":    s.config.Version,
			"request_id": c.GetString("request_id"),
			"code":       "CATALOG_LOAD_FAILED",
		})
		return
	}
	s.healthResponse(c, "ready")
}

func (s *Server) initMetrics() {
	reg := prometheus.NewRegistry()
	info := prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "service_build_info",
			Help: "Service build information",
		},
		[]string{"service", "version"},
	)
	reg.MustRegister(info)
	s.registerCount.Add(1)
	info.WithLabelValues(s.config.Service, s.config.Version).Set(1)
	s.metricsReg = reg
	s.metricsHandler = promhttp.HandlerFor(reg, promhttp.HandlerOpts{})
}

func (s *Server) MetricsRegisterCount() int {
	return int(s.registerCount.Load())
}

func (s *Server) metrics(c *gin.Context) {
	s.metricsHandler.ServeHTTP(c.Writer, c.Request)
}

func (s *Server) notFound(c *gin.Context) {
	c.JSON(http.StatusNotFound, gin.H{
		"service":    s.config.Service,
		"status":     "not_found",
		"version":    s.config.Version,
		"request_id": c.GetString("request_id"),
	})
}

func requestIDMiddleware(logger *slog.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		rid := c.GetHeader("X-Request-ID")
		if rid == "" {
			b := make([]byte, 16)
			if _, err := rand.Read(b); err == nil {
				rid = fmt.Sprintf("%x", b)
			} else {
				rid = "unknown"
			}
		}
		c.Set("request_id", rid)
		c.Header("X-Request-ID", rid)

		req := c.Request
		logger.Info("request",
			"method", req.Method,
			"path", req.URL.Path,
			"request_id", rid,
			"headers", SanitizeHeaders(req.Header),
		)
		c.Next()
	}
}

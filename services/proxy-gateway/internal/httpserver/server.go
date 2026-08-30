// Package httpserver provides the SF01 operational HTTP surface for the proxy
// gateway (liveness/readiness/metrics) plus optional internal credential validation.
package httpserver

import (
	"context"
	"crypto/rand"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
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
	Passthrough   *PassthroughDeps
	// CatalogReady 非 nil 且为 false 时 readiness 失败关闭（目录未锁定）。
	CatalogReady *bool
}

// Server wraps the Gin engine and configuration.
type Server struct {
	config         Config
	engine         *gin.Engine
	validateDeps   *ValidateDeps
	proxyEnabled   bool
	passthrough    *PassthroughDeps
	metricsHandler http.Handler
	metricsReg     prometheus.Registerer
	registerCount  atomic.Int32
	draining       atomic.Bool
	inflight       sync.WaitGroup
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
	r.Use(s.drainMiddleware())
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
	if cfg.Passthrough != nil && cfg.Passthrough.Kernel != nil {
		s.registerPassthrough(*cfg.Passthrough)
		r.NoRoute(nativeOrNotFound(s))
	} else {
		r.NoRoute(s.notFound)
	}
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
	if s.draining.Load() {
		c.JSON(http.StatusServiceUnavailable, gin.H{
			"service":    s.config.Service,
			"status":     "not_ready",
			"version":    s.config.Version,
			"request_id": c.GetString("request_id"),
			"code":       "NOT_READY",
		})
		return
	}
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

func (s *Server) drainMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		path := c.Request.URL.Path
		if path == "/health/live" || path == "/metrics" || path == "/health/ready" {
			c.Next()
			return
		}
		if s.draining.Load() {
			c.JSON(http.StatusServiceUnavailable, gin.H{
				"service":    s.config.Service,
				"status":     "not_ready",
				"version":    s.config.Version,
				"request_id": c.GetString("request_id"),
				"code":       "NOT_READY",
			})
			c.Abort()
			return
		}
		s.inflight.Add(1)
		defer s.inflight.Done()
		c.Next()
	}
}

// BeginWork 测试/排空记账：摘流后返回 false。
func (s *Server) BeginWork() bool {
	if s == nil || s.draining.Load() {
		return false
	}
	s.inflight.Add(1)
	return true
}

func (s *Server) EndWork() {
	if s != nil {
		s.inflight.Done()
	}
}

// Drain 拒绝新请求并等待在途结束或 ctx 取消。
func (s *Server) Drain(ctx context.Context) error {
	s.draining.Store(true)
	done := make(chan struct{})
	go func() {
		s.inflight.Wait()
		close(done)
	}()
	select {
	case <-done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
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

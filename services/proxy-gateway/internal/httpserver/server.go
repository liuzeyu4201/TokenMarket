// Package httpserver provides the SF01 operational HTTP surface for the proxy
// gateway. It exposes liveness, readiness and metrics endpoints and no business
// routes.
package httpserver

import (
	"crypto/rand"
	"fmt"
	"log/slog"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

// Config holds server construction parameters.
type Config struct {
	Service string
	Version string
	Logger  *slog.Logger
}

// Server wraps the Gin engine and configuration.
type Server struct {
	config Config
	engine *gin.Engine
}

// NewServer creates an operational scaffold server.
func NewServer(cfg Config) (*Server, error) {
	if cfg.Logger == nil {
		cfg.Logger = slog.Default()
	}
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(requestIDMiddleware(cfg.Logger))
	r.Use(gin.Recovery())

	s := &Server{config: cfg, engine: r}
	r.GET("/health/live", s.liveness)
	r.GET("/health/ready", s.readiness)
	r.GET("/metrics", s.metrics)
	r.NoRoute(s.notFound)
	return s, nil
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
	s.healthResponse(c, "ready")
}

func (s *Server) metrics(c *gin.Context) {
	info := prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "service_build_info",
			Help: "Service build information",
		},
		[]string{"service", "version"},
	)
	info.WithLabelValues(s.config.Service, s.config.Version).Set(1)
	prometheus.MustRegister(info)
	defer prometheus.Unregister(info)
	promhttp.Handler().ServeHTTP(c.Writer, c.Request)
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

		// Redact common secret headers before logging.
		req := c.Request
		cleanHeaders := make(http.Header, len(req.Header))
		for k, v := range req.Header {
			lower := strings.ToLower(k)
			if lower == "authorization" || strings.Contains(lower, "secret") || strings.Contains(lower, "api-key") {
				cleanHeaders.Set(k, "[REDACTED]")
			} else {
				cleanHeaders[k] = v
			}
		}

		logger.Info("request",
			"method", req.Method,
			"path", req.URL.Path,
			"request_id", rid,
			"headers", cleanHeaders,
		)
		c.Next()
	}
}

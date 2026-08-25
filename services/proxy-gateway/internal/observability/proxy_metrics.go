package observability

import (
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

// ProxyHTTPMetrics 公开代理入口低基数指标（SF19）。
type ProxyHTTPMetrics struct {
	requests *prometheus.CounterVec
	duration *prometheus.HistogramVec
	capacity prometheus.Counter
	authFail prometheus.Counter
	usage    *prometheus.CounterVec
	health   *prometheus.CounterVec
}

var defaultProxyHTTP *ProxyHTTPMetrics
var defaultProxyOnce sync.Once

func DefaultProxyHTTPMetrics() *ProxyHTTPMetrics {
	defaultProxyOnce.Do(func() {
		defaultProxyHTTP = NewProxyHTTPMetrics()
		defaultProxyHTTP.MustRegister(prometheus.DefaultRegisterer)
	})
	return defaultProxyHTTP
}

func NewProxyHTTPMetrics() *ProxyHTTPMetrics {
	return &ProxyHTTPMetrics{
		requests: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "proxy_requests_total",
			Help: "Public proxy chat completions by bounded result class",
		}, []string{"platform", "stream", "result"}),
		duration: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "proxy_request_duration_seconds",
			Help:    "Public proxy end-to-end duration",
			Buckets: []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 8, 30, 60},
		}, []string{"platform", "stream"}),
		capacity: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "proxy_capacity_rejected_total",
			Help: "Requests rejected because no routable seller key had capacity",
		}),
		authFail: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "proxy_auth_failures_total",
			Help: "Proxy key authentication failures (no existence leak)",
		}),
		usage: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "provider_usage_observe_total",
			Help: "Usage completion observations by persist result",
		}, []string{"result"}),
		health: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "provider_health_check_total",
			Help: "Seller key health probes by result class",
		}, []string{"platform", "result"}),
	}
}

func (m *ProxyHTTPMetrics) MustRegister(r prometheus.Registerer) {
	r.MustRegister(m.requests, m.duration, m.capacity, m.authFail, m.usage, m.health)
}

func (m *ProxyHTTPMetrics) ObserveRequest(platform, stream, result string, d time.Duration) {
	if m == nil {
		return
	}
	if platform == "" {
		platform = "volcano"
	}
	m.requests.WithLabelValues(platform, stream, result).Inc()
	m.duration.WithLabelValues(platform, stream).Observe(d.Seconds())
}

func (m *ProxyHTTPMetrics) AuthFail() {
	if m != nil {
		m.authFail.Inc()
	}
}

func (m *ProxyHTTPMetrics) CapacityReject() {
	if m != nil {
		m.capacity.Inc()
	}
}

func (m *ProxyHTTPMetrics) Usage(result string) {
	if m != nil {
		m.usage.WithLabelValues(result).Inc()
	}
}

func (m *ProxyHTTPMetrics) Health(platform, result string) {
	if m != nil {
		if platform == "" {
			platform = "volcano"
		}
		m.health.WithLabelValues(platform, result).Inc()
	}
}

// ResultClass 将 HTTP 状态映射为有界 result 标签（4xx 客户端 vs 5xx 系统）。
func ResultClass(status int) string {
	switch {
	case status == 401:
		return "auth_error"
	case status == 429:
		return "rate_limited"
	case status == 503:
		return "no_capacity"
	case status >= 400 && status < 500:
		return "client_error"
	case status >= 500:
		return "system_error"
	default:
		return "success"
	}
}

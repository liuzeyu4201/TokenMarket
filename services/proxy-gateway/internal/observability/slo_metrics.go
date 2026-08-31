package observability

import (
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

// SLOMetrics is the bounded RED / stream / backlog surface (SF32).
type SLOMetrics struct {
	requests      *prometheus.CounterVec
	platform      *prometheus.HistogramVec
	upstream      *prometheus.HistogramVec
	streamConnect *prometheus.HistogramVec
	streamFirst   *prometheus.HistogramVec
	streamDur     *prometheus.HistogramVec
	streamClose   *prometheus.CounterVec
	noCandidate   prometheus.Counter
	backlog       prometheus.Gauge
	unresolved    prometheus.Gauge
	connHealth    *prometheus.GaugeVec
}

func NewSLOMetrics() *SLOMetrics {
	buckets := []float64{0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 8, 30, 60}
	return &SLOMetrics{
		requests: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "proxy_slo_requests_total",
			Help: "SLO requests by plane/protocol/endpoint/status",
		}, []string{"plane", "protocol", "endpoint", "status"}),
		platform: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "proxy_platform_duration_seconds",
			Help:    "Platform-added latency excluding upstream",
			Buckets: buckets,
		}, []string{"protocol", "endpoint"}),
		upstream: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "proxy_upstream_duration_seconds",
			Help:    "Upstream round-trip latency",
			Buckets: buckets,
		}, []string{"protocol", "endpoint"}),
		streamConnect: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "proxy_stream_connect_seconds",
			Help:    "SSE/WebSocket time to connect",
			Buckets: buckets,
		}, []string{"protocol"}),
		streamFirst: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "proxy_stream_first_event_seconds",
			Help:    "SSE/WebSocket time to first event",
			Buckets: buckets,
		}, []string{"protocol"}),
		streamDur: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "proxy_stream_duration_seconds",
			Help:    "SSE/WebSocket stream lifetime",
			Buckets: buckets,
		}, []string{"protocol"}),
		streamClose: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "proxy_stream_close_total",
			Help: "SSE/WebSocket close reasons",
		}, []string{"protocol", "reason"}),
		noCandidate: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "proxy_route_no_candidate_total",
			Help: "Route decisions with an empty qualified set",
		}),
		backlog: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "proxy_event_backlog",
			Help: "Usage/settlement event backlog depth",
		}),
		unresolved: prometheus.NewGauge(prometheus.GaugeOpts{
			Name: "proxy_unresolved_total",
			Help: "Open unresolved ledger cases",
		}),
		connHealth: prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "proxy_connection_health",
			Help: "Connection health samples by bounded state",
		}, []string{"state"}),
	}
}

func (m *SLOMetrics) MustRegister(r prometheus.Registerer) {
	r.MustRegister(
		m.requests,
		m.platform,
		m.upstream,
		m.streamConnect,
		m.streamFirst,
		m.streamDur,
		m.streamClose,
		m.noCandidate,
		m.backlog,
		m.unresolved,
		m.connHealth,
	)
}

func (m *SLOMetrics) ObserveRED(plane, protocol, endpoint, status string, platform, upstream time.Duration) {
	if m == nil {
		return
	}
	if plane == "" {
		plane = "dataplane"
	}
	if protocol == "" {
		protocol = "openai"
	}
	if endpoint == "" {
		endpoint = "unknown"
	}
	if status == "" {
		status = "200"
	}
	m.requests.WithLabelValues(plane, protocol, endpoint, status).Inc()
	m.platform.WithLabelValues(protocol, endpoint).Observe(platform.Seconds())
	m.upstream.WithLabelValues(protocol, endpoint).Observe(upstream.Seconds())
}

func (m *SLOMetrics) ObserveStream(protocol, phase string, d time.Duration, reason string) {
	if m == nil {
		return
	}
	if protocol == "" {
		protocol = "openai"
	}
	switch phase {
	case "connect":
		m.streamConnect.WithLabelValues(protocol).Observe(d.Seconds())
	case "first_event":
		m.streamFirst.WithLabelValues(protocol).Observe(d.Seconds())
	default:
		m.streamDur.WithLabelValues(protocol).Observe(d.Seconds())
		if reason == "" {
			reason = "complete"
		}
		m.streamClose.WithLabelValues(protocol, reason).Inc()
	}
}

func (m *SLOMetrics) ObserveNoCandidate() {
	if m != nil {
		m.noCandidate.Inc()
	}
}

func (m *SLOMetrics) SetBacklog(n float64) {
	if m != nil {
		m.backlog.Set(n)
	}
}

func (m *SLOMetrics) SetUnresolved(n float64) {
	if m != nil {
		m.unresolved.Set(n)
	}
}

func (m *SLOMetrics) SetConnectionHealth(state string, n float64) {
	if m == nil {
		return
	}
	if state == "" {
		state = "unknown"
	}
	m.connHealth.WithLabelValues(state).Set(n)
}

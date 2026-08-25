package observability

import (
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

// ChatMetrics 适配路径指标。
type ChatMetrics struct {
	total     *prometheus.CounterVec
	duration  *prometheus.HistogramVec
	truncated prometheus.Counter
}

var defaultChatMetrics *ChatMetrics
var defaultChatOnce sync.Once

func DefaultChatMetrics() *ChatMetrics {
	defaultChatOnce.Do(func() {
		defaultChatMetrics = NewChatMetrics()
		defaultChatMetrics.MustRegister(prometheus.DefaultRegisterer)
	})
	return defaultChatMetrics
}

func NewChatMetrics() *ChatMetrics {
	return &ChatMetrics{
		total: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "provider_chat_total",
			Help: "Volcano chat adapter results",
		}, []string{"platform", "stream", "error_category"}),
		duration: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "provider_chat_duration_seconds",
			Help:    "Volcano chat adapter duration",
			Buckets: []float64{0.001, 0.005, 0.025, 0.1, 0.5, 1, 5, 30, 60},
		}, []string{"platform", "stream"}),
		truncated: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "provider_chat_truncated_total",
			Help: "Stream truncations after at least one event",
		}),
	}
}

func (m *ChatMetrics) MustRegister(r prometheus.Registerer) {
	r.MustRegister(m.total, m.duration, m.truncated)
}

func (m *ChatMetrics) Observe(platform string, stream bool, category string, d time.Duration) {
	if m == nil {
		return
	}
	sv := "false"
	if stream {
		sv = "true"
	}
	m.total.WithLabelValues(platform, sv, category).Inc()
	m.duration.WithLabelValues(platform, sv).Observe(d.Seconds())
}

func (m *ChatMetrics) Truncated() {
	if m != nil {
		m.truncated.Inc()
	}
}

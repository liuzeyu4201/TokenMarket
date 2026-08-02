package observability

import (
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
)

// ValidateMetrics 验证路径指标（低基数）。
type ValidateMetrics struct {
	total    *prometheus.CounterVec
	duration *prometheus.HistogramVec
	gate     prometheus.Counter
	regOnce  sync.Once
}

var defaultValidateMetrics *ValidateMetrics
var defaultValidateOnce sync.Once

// DefaultValidateMetrics 进程单例（注册一次）。
func DefaultValidateMetrics() *ValidateMetrics {
	defaultValidateOnce.Do(func() {
		defaultValidateMetrics = NewValidateMetrics()
		defaultValidateMetrics.MustRegister(prometheus.DefaultRegisterer)
	})
	return defaultValidateMetrics
}

// NewValidateMetrics 创建未注册指标。
func NewValidateMetrics() *ValidateMetrics {
	return &ValidateMetrics{
		total: prometheus.NewCounterVec(prometheus.CounterOpts{
			Name: "provider_validate_total",
			Help: "Provider credential validation results",
		}, []string{"platform", "error_category"}),
		duration: prometheus.NewHistogramVec(prometheus.HistogramOpts{
			Name:    "provider_validate_duration_seconds",
			Help:    "Provider credential validation duration",
			Buckets: []float64{0.05, 0.1, 0.25, 0.5, 1, 2, 3},
		}, []string{"platform"}),
		gate: prometheus.NewCounter(prometheus.CounterOpts{
			Name: "provider_validate_gate_rejected_total",
			Help: "Validation concurrency gate rejections",
		}),
	}
}

// MustRegister 注册到 registerer。
func (m *ValidateMetrics) MustRegister(r prometheus.Registerer) {
	if m == nil {
		return
	}
	m.regOnce.Do(func() {
		r.MustRegister(m.total, m.duration, m.gate)
	})
}

// Observe 记录结果；platform 为请求平台（规范化后），不得硬编码 volcano。
func (m *ValidateMetrics) Observe(platform, errorCategory string, d time.Duration) {
	if m == nil {
		return
	}
	if platform == "" {
		platform = "unknown"
	}
	if errorCategory == "" {
		errorCategory = "unknown"
	}
	m.total.WithLabelValues(platform, errorCategory).Inc()
	m.duration.WithLabelValues(platform).Observe(d.Seconds())
}

// GateRejected 闸门拒绝。
func (m *ValidateMetrics) GateRejected() {
	if m == nil {
		return
	}
	m.gate.Inc()
}

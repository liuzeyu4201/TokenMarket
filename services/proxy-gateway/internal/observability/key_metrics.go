package observability

import (
	"sync"

	"github.com/prometheus/client_golang/prometheus"
)

// KeyStatus 库存快照的有界状态（无 key_id）。
type KeyStatus struct {
	Admin  string
	Health string
}

// KeyInventoryMetrics 低基数 Key 状态（SF19 FR-003）。
type KeyInventoryMetrics struct {
	byStatus *prometheus.GaugeVec
}

var defaultKeyInventory *KeyInventoryMetrics
var defaultKeyInventoryOnce sync.Once

func DefaultKeyInventoryMetrics() *KeyInventoryMetrics {
	defaultKeyInventoryOnce.Do(func() {
		defaultKeyInventory = NewKeyInventoryMetrics()
		defaultKeyInventory.MustRegister(prometheus.DefaultRegisterer)
	})
	return defaultKeyInventory
}

func NewKeyInventoryMetrics() *KeyInventoryMetrics {
	return &KeyInventoryMetrics{
		byStatus: prometheus.NewGaugeVec(prometheus.GaugeOpts{
			Name: "provider_key_inventory",
			Help: "Seller key counts by platform and status",
		}, []string{"platform", "status"}),
	}
}

func (m *KeyInventoryMetrics) MustRegister(r prometheus.Registerer) {
	r.MustRegister(m.byStatus)
}

func (m *KeyInventoryMetrics) Set(platform, status string, n float64) {
	if m != nil {
		m.byStatus.WithLabelValues(platform, status).Set(n)
	}
}

var inventoryStatuses = []string{
	"active", "paused", "revoked",
	"healthy", "down", "rate_limited", "expired", "invalid", "unknown",
	"routable",
}

// Publish 用当前快照覆盖全部有界 status 标签（含 0，避免陈旧非零）。
func (m *KeyInventoryMetrics) Publish(platform string, rows []KeyStatus) {
	if m == nil {
		return
	}
	if platform == "" {
		platform = "volcano"
	}
	counts := make(map[string]float64, len(inventoryStatuses))
	for _, s := range inventoryStatuses {
		counts[s] = 0
	}
	for _, row := range rows {
		if row.Admin != "" {
			counts[row.Admin]++
		}
		if row.Health != "" {
			counts[row.Health]++
		}
		if row.Admin == "active" && row.Health == "healthy" {
			counts["routable"]++
		}
	}
	for _, s := range inventoryStatuses {
		m.Set(platform, s, counts[s])
	}
}

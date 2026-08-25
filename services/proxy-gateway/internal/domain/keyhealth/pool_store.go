package keyhealth

import (
	"context"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keypool"
)

// HealthSink 把健康状态写回持久事实源（API）。可选。
type HealthSink interface {
	PatchHealth(ctx context.Context, id, health string) error
}

// PoolStore 以 Key 池快照为探活列表，并把结果写回池（及可选 API）。
type PoolStore struct {
	Pool *keypool.Pool
	API  HealthSink
}

func (p PoolStore) ListActive(ctx context.Context) []KeyFact {
	if p.Pool == nil {
		return nil
	}
	snap := p.Pool.Snapshot()
	out := make([]KeyFact, 0, len(snap))
	for _, k := range snap {
		out = append(out, KeyFact{ID: k.ID, APIKey: k.APIKey, Health: k.Health, Admin: k.Admin})
	}
	return out
}

func (p PoolStore) ApplyHealth(ctx context.Context, id, health string) error {
	if p.Pool != nil {
		p.Pool.UpdateHealth(id, health)
	}
	if p.API != nil {
		return p.API.PatchHealth(ctx, id, health)
	}
	return nil
}

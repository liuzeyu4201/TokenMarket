package keypool

import (
	"context"
	"strconv"
	"strings"
	"sync"
	"time"
)

// SellerKey 可路由候选。
type SellerKey struct {
	ID             string
	SellerID       string
	APIKey         string
	Admin          string
	Health         string
	Platform       string
	RemainingQuota string
	MaxInflight    int
}

// AllocableConcurrency 官方并发上限的向下取整 80%，至少 1；未知则保守默认 32（SF14）。
func AllocableConcurrency(official int) int {
	if official <= 0 {
		return 32
	}
	n := official * 80 / 100
	if n < 1 {
		return 1
	}
	return n
}

func PositiveQuota(q string) bool {
	q = strings.TrimSpace(q)
	if q == "" {
		return true
	}
	f, err := strconv.ParseFloat(q, 64)
	if err != nil {
		return true
	}
	return f > 0
}

func Routable(k SellerKey) bool {
	return k.Admin == "active" && k.Health == "healthy" && PositiveQuota(k.RemainingQuota)
}

// Source 从持久事实刷新候选（API 内部接口或测试夹具）。
type Source interface {
	List(ctx context.Context) ([]SellerKey, error)
}

// StaticSource 进程内快照。
type StaticSource struct{ Keys []SellerKey }

func (s StaticSource) List(context.Context) ([]SellerKey, error) { return s.Keys, nil }

// Pool 轮询选择 + 单 Key 进行中上限（SF13/SF14）。
type Pool struct {
	mu          sync.Mutex
	idx         int
	keys        []SellerKey
	inflight    map[string]int
	coolUntil   map[string]time.Time
	maxInflight int
	src         Source
}

func New(keys []SellerKey, maxInflight int) *Pool {
	if maxInflight < 1 {
		maxInflight = 32
	}
	return &Pool{
		keys: keys, inflight: map[string]int{}, coolUntil: map[string]time.Time{},
		maxInflight: maxInflight, src: StaticSource{Keys: keys},
	}
}

func NewFromSource(src Source, maxInflight int) *Pool {
	p := New(nil, maxInflight)
	p.src = src
	return p
}

// Refresh 从 Source 替换候选（保留 inflight 计数）。
func (p *Pool) Refresh(ctx context.Context) error {
	if p.src == nil {
		return nil
	}
	keys, err := p.src.List(ctx)
	if err != nil {
		return err
	}
	p.mu.Lock()
	p.keys = keys
	p.mu.Unlock()
	return nil
}

// Pick 选择可路由 Key，排除 buyer 自己的卖家 Key（SF05/SF13）。
func (p *Pool) Pick(excludeSellerID string) (SellerKey, bool) {
	p.mu.Lock()
	defer p.mu.Unlock()
	n := len(p.keys)
	if n == 0 {
		return SellerKey{}, false
	}
	for i := 0; i < n; i++ {
		p.idx = (p.idx + 1) % n
		k := p.keys[p.idx]
		if !Routable(k) {
			continue
		}
		if excludeSellerID != "" && k.SellerID == excludeSellerID {
			continue
		}
		if until, ok := p.coolUntil[k.ID]; ok && time.Now().Before(until) {
			continue
		}
		capn := p.maxInflight
		if k.MaxInflight > 0 {
			capn = k.MaxInflight
		}
		if p.inflight[k.ID] >= capn {
			continue
		}
		p.inflight[k.ID]++
		return k, true
	}
	return SellerKey{}, false
}

// Cooldown 请求级 429 冷却（默认 30s；更长 Retry-After 由调用方传入）。
func (p *Pool) Cooldown(id string, d time.Duration) {
	if id == "" {
		return
	}
	if d <= 0 {
		d = 30 * time.Second
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.coolUntil == nil {
		p.coolUntil = map[string]time.Time{}
	}
	p.coolUntil[id] = time.Now().Add(d)
}

func (p *Pool) Release(id string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.inflight[id] > 0 {
		p.inflight[id]--
	}
}

func (p *Pool) Snapshot() []SellerKey {
	p.mu.Lock()
	defer p.mu.Unlock()
	out := make([]SellerKey, len(p.keys))
	copy(out, p.keys)
	return out
}

// UpdateHealth 更新池内健康状态；下一轮 Pick 立即生效。
func (p *Pool) UpdateHealth(id, health string) {
	p.mu.Lock()
	defer p.mu.Unlock()
	for i := range p.keys {
		if p.keys[i].ID == id {
			p.keys[i].Health = health
			return
		}
	}
}

// ReplaceKey 按 ID 替换一条候选（刷新单 Key 而不丢 inflight）。
func (p *Pool) ReplaceKey(k SellerKey) {
	p.mu.Lock()
	defer p.mu.Unlock()
	for i := range p.keys {
		if p.keys[i].ID == k.ID {
			p.keys[i] = k
			return
		}
	}
	p.keys = append(p.keys, k)
}

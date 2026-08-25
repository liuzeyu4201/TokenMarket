package keyhealth

import (
	"context"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

// KeyFact 待探活的卖家 Key。
type KeyFact struct {
	ID     string
	APIKey string
	Health string
	Admin  string
}

// Store 健康状态事实源。
type Store interface {
	ListActive(ctx context.Context) []KeyFact
	ApplyHealth(ctx context.Context, id, health string) error
}

// Probe 调用 SF06 分类。
type Probe func(ctx context.Context, apiKey string) providervalid.ErrorCategory

// OnProbe 每次探活完成后的低基数观察（platform, result）。
type OnProbe func(platform, result string)

// Scheduler 周期健康检查（默认 30s）。
type Scheduler struct {
	Interval time.Duration
	Store    Store
	Probe    Probe
	OnProbe  OnProbe
	Now      func() time.Time
	fails    map[string]int
	until    map[string]time.Time
}

func (s *Scheduler) now() time.Time {
	if s != nil && s.Now != nil {
		return s.Now()
	}
	return time.Now()
}

func (s *Scheduler) Tick(ctx context.Context) int {
	if s.Store == nil || s.Probe == nil {
		return 0
	}
	if s.fails == nil {
		s.fails = map[string]int{}
	}
	if s.until == nil {
		s.until = map[string]time.Time{}
	}
	n := 0
	for _, k := range s.Store.ListActive(ctx) {
		if k.Admin != "active" {
			continue
		}
		if until, ok := s.until[k.ID]; ok && s.now().Before(until) {
			continue
		}
		cat := s.Probe(ctx, k.APIKey)
		if s.OnProbe != nil {
			s.OnProbe("volcano", string(cat))
		}
		health, skipApply := nextFromProbe(k, cat, s)
		if skipApply {
			continue
		}
		if health == k.Health {
			continue
		}
		if k.Health == "invalid" && health != "invalid" && health != "healthy" {
			continue
		}
		_ = s.Store.ApplyHealth(ctx, k.ID, health)
		n++
	}
	return n
}

func nextFromProbe(k KeyFact, cat providervalid.ErrorCategory, s *Scheduler) (health string, skip bool) {
	switch cat {
	case providervalid.CategorySuccess:
		s.fails[k.ID] = 0
		delete(s.until, k.ID)
		return "healthy", false
	case providervalid.CategoryTimeout, providervalid.CategoryTemporaryUnavailable:
		s.fails[k.ID]++
		if s.fails[k.ID] < 3 {
			return k.Health, true
		}
		return "down", false
	case providervalid.CategoryRateLimited:
		s.until[k.ID] = s.now().Add(30 * time.Minute)
		return "rate_limited", false
	default:
		h, _ := MapValidateCategory(cat)
		return h, false
	}
}

func (s *Scheduler) Run(ctx context.Context) {
	iv := s.Interval
	if iv <= 0 {
		iv = 30 * time.Second
	}
	t := time.NewTicker(iv)
	defer t.Stop()
	s.Tick(ctx)
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			s.Tick(ctx)
		}
	}
}

func NextHealth(prev string, cat providervalid.ErrorCategory) string {
	h, _ := MapValidateCategory(cat)
	if prev == "invalid" && h != "healthy" && h != "invalid" {
		return prev
	}
	return h
}

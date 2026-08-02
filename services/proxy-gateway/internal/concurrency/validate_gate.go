// Package concurrency 提供验证全局/单凭证并发闸门。
package concurrency

import (
	"sync"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

// ValidateGate 进程内信号量。
type ValidateGate struct {
	globalLimit  int
	perCredLimit int
	secret       string

	mu      sync.Mutex
	global  int
	perCred map[string]int
}

// NewValidateGate 构造闸门。
func NewValidateGate(globalLimit, perCredLimit int, hmacSecret string) *ValidateGate {
	if globalLimit < 1 {
		globalLimit = 32
	}
	if perCredLimit < 1 {
		perCredLimit = 1
	}
	return &ValidateGate{
		globalLimit:  globalLimit,
		perCredLimit: perCredLimit,
		secret:       hmacSecret,
		perCred:      make(map[string]int),
	}
}

// Acquire 尝试占用；ok=false 表示超限，不应发起上游调用。
func (g *ValidateGate) Acquire(apiKey string) (release func(), ok bool) {
	key := providervalid.CredentialRef(apiKey, g.secret)
	g.mu.Lock()
	defer g.mu.Unlock()
	if g.global >= g.globalLimit {
		return nil, false
	}
	if g.perCred[key] >= g.perCredLimit {
		return nil, false
	}
	g.global++
	g.perCred[key]++
	released := false
	return func() {
		g.mu.Lock()
		defer g.mu.Unlock()
		if released {
			return
		}
		released = true
		g.global--
		g.perCred[key]--
		if g.perCred[key] <= 0 {
			delete(g.perCred, key)
		}
	}, true
}

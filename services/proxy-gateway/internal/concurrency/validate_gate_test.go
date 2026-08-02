package concurrency_test

import (
	"sync"
	"sync/atomic"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/concurrency"
)

func TestGateGlobalLimit(t *testing.T) {
	g := concurrency.NewValidateGate(2, 10, "sec")
	r1, ok1 := g.Acquire("k1")
	r2, ok2 := g.Acquire("k2")
	if !ok1 || !ok2 {
		t.Fatal("first two")
	}
	_, ok3 := g.Acquire("k3")
	if ok3 {
		t.Fatal("third should fail")
	}
	r1()
	r2()
	_, ok4 := g.Acquire("k4")
	if !ok4 {
		t.Fatal("after release")
	}
}

func TestGatePerCredential(t *testing.T) {
	g := concurrency.NewValidateGate(32, 1, "sec")
	r1, ok1 := g.Acquire("same-key")
	if !ok1 {
		t.Fatal("first")
	}
	_, ok2 := g.Acquire("same-key")
	if ok2 {
		t.Fatal("second same key")
	}
	r1()
	_, ok3 := g.Acquire("same-key")
	if !ok3 {
		t.Fatal("after release")
	}
}

func TestGateNoDownstreamOnReject(t *testing.T) {
	g := concurrency.NewValidateGate(1, 1, "sec")
	rel, _ := g.Acquire("a")
	defer rel()
	var calls atomic.Int32
	if _, ok := g.Acquire("b"); !ok {
		// rejected — do not call downstream
	} else {
		calls.Add(1)
	}
	if calls.Load() != 0 {
		t.Fatal("downstream called")
	}
}

func TestGateConcurrent(t *testing.T) {
	g := concurrency.NewValidateGate(32, 1, "sec")
	var wg sync.WaitGroup
	var okCount atomic.Int32
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if rel, ok := g.Acquire("k"); ok {
				okCount.Add(1)
				rel()
			}
		}()
	}
	wg.Wait()
	if okCount.Load() < 1 {
		t.Fatal("expected some ok")
	}
}

// TestGateDefaultGlobal32Rejects33rd 验收 SC-002a：默认全局 32 时第 33 路拒绝。
func TestGateDefaultGlobal32Rejects33rd(t *testing.T) {
	g := concurrency.NewValidateGate(32, 10, "sec")
	releases := make([]func(), 0, 32)
	for i := 0; i < 32; i++ {
		key := "k-" + string(rune('a'+i%26)) + string(rune('0'+i/26))
		// unique keys to avoid per-cred limit
		rel, ok := g.Acquire("unique-key-" + itoa(i))
		if !ok {
			t.Fatalf("acquire %d should succeed", i)
		}
		releases = append(releases, rel)
		_ = key
	}
	if _, ok := g.Acquire("unique-key-33"); ok {
		t.Fatal("33rd global acquire must fail")
	}
	for _, r := range releases {
		r()
	}
}

// TestGateDefaultPerCred1RejectsSecond 验收 SC-002a：单凭证默认 1，第 2 路拒绝。
func TestGateDefaultPerCred1RejectsSecond(t *testing.T) {
	g := concurrency.NewValidateGate(32, 1, "sec")
	rel, ok := g.Acquire("same-default-key")
	if !ok {
		t.Fatal("first")
	}
	defer rel()
	if _, ok := g.Acquire("same-default-key"); ok {
		t.Fatal("second same key must fail under per-cred=1")
	}
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var b [12]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	return string(b[i:])
}

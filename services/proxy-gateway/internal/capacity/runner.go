package capacity

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"runtime"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/passthrough"
)

var httpClient = &http.Client{Timeout: 15 * time.Second}

type Engine struct {
	Mock   *MockUpstream
	Ledger *MemLedger
	kernel *passthrough.Kernel
	proxy  *httptest.Server
	up     *httptest.Server
	seq    *atomic.Int64
}

func NewEngine() *Engine {
	return NewEngineWithLedger(NewMemLedger(), new(atomic.Int64), nil)
}

// NewEngineWithLedger shares one SoR ledger (and optional quota wrapper) across nodes.
func NewEngineWithLedger(led *MemLedger, seq *atomic.Int64, quota passthrough.Quota) *Engine {
	if led == nil {
		led = NewMemLedger()
	}
	if seq == nil {
		seq = new(atomic.Int64)
	}
	if quota == nil {
		quota = led
	}
	mock := &MockUpstream{}
	up := httptest.NewServer(mock)
	k := &passthrough.Kernel{
		Catalog:  Catalog(),
		Selector: passthrough.StaticSelector{Up: passthrough.Upstream{BaseURL: up.URL, Credential: "mock-k"}},
		Limits: passthrough.Limits{
			IdleTimeout:     30 * time.Second,
			UpstreamTimeout: StreamDuration + 5*time.Second,
		},
		Quota: quota,
	}
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		k.ServeHTTP(w, r, "shared", false)
	}))
	return &Engine{Mock: mock, Ledger: led, kernel: k, proxy: proxy, up: up, seq: seq}
}

func (e *Engine) Close() {
	if e.proxy != nil {
		e.proxy.Close()
	}
	if e.up != nil {
		e.up.Close()
	}
}

func (e *Engine) Run(p Profile) Report {
	tenants := Dataset(DatasetSeed, p.Tenants)
	var total, ok atomic.Int64
	var mu sync.Mutex
	lats := make([]time.Duration, 0, 1024)
	start := time.Now()
	end := start.Add(p.Duration)
	interval := time.Second
	if p.RPS > 0 {
		interval = time.Second / time.Duration(p.RPS)
	}
	tick := time.NewTicker(interval)
	defer tick.Stop()
	var wg sync.WaitGroup
	i := 0
	for time.Now().Before(end) {
		<-tick.C
		if !time.Now().Before(end) {
			break
		}
		tn := tenants[i%len(tenants)]
		i++
		wg.Add(1)
		go func() {
			defer wg.Done()
			rid := fmt.Sprintf("cap-%d", e.seq.Add(1))
			status, plat := e.once(tn, rid)
			total.Add(1)
			if status >= 200 && status < 300 {
				ok.Add(1)
				e.Ledger.Settle(rid)
			} else {
				_ = e.Ledger.Abort(context.Background(), rid)
			}
			mu.Lock()
			lats = append(lats, plat)
			mu.Unlock()
		}()
	}
	wg.Wait()
	elapsed := time.Since(start)
	rep := Report{
		Profile:          p.Name,
		Tenants:          p.Tenants,
		TargetRPS:        float64(p.RPS),
		Duration:         elapsed,
		DurationMS:       elapsed.Milliseconds(),
		Total:            int(total.Load()),
		Success:          int(ok.Load()),
		OpenReservations: e.Ledger.OpenCount(),
		DoubleCharge:     e.Ledger.DoubleCharge,
		CrossTenantLeaks: e.Ledger.Leaks,
	}
	if elapsed.Seconds() > 0 {
		rep.AchievedRPS = float64(rep.Total) / elapsed.Seconds()
	}
	if rep.Total > 0 {
		rep.SuccessRate = float64(rep.Success) / float64(rep.Total)
	}
	rep.PlatformP95 = percentile(lats, 0.95)
	rep.PlatformP95MS = float64(rep.PlatformP95) / float64(time.Millisecond)
	rep.Pass = rep.PassSteady()
	return rep
}

func (e *Engine) Retry(tn Tenant, rid string) int {
	status, _ := e.once(tn, rid)
	if status >= 200 && status < 300 {
		if !e.Ledger.AlreadySettled(rid) {
			e.Ledger.Settle(rid)
		}
	} else {
		_ = e.Ledger.Abort(context.Background(), rid)
	}
	return status
}

func (e *Engine) once(tn Tenant, rid string) (int, time.Duration) {
	body := `{"model":"m","messages":[{"role":"user","content":"hi"}]}`
	req, err := http.NewRequest(http.MethodPost, e.proxy.URL+tn.Path(), strings.NewReader(body))
	if err != nil {
		return 0, 0
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Request-ID", rid)
	req.Header.Set("X-TokenMarket-Project-ID", tn.ProjectID)
	req.Header.Set("X-TokenMarket-Key-ID", tn.KeyID)
	start := time.Now()
	resp, err := httpClient.Do(req)
	plat := time.Since(start)
	if err != nil {
		return 0, plat
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	return resp.StatusCode, plat
}

func (e *Engine) RunStream(n int, d time.Duration) Report {
	var startHeap runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&startHeap)
	tenants := Dataset(DatasetSeed, TenantCount)
	e.Mock.SetHold(d)
	defer e.Mock.SetHold(0)
	var fail, done atomic.Int64
	var wg sync.WaitGroup
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			tn := tenants[i%len(tenants)]
			rid := fmt.Sprintf("sse-%d", e.seq.Add(1))
			ctx, cancel := context.WithTimeout(context.Background(), d+2*time.Second)
			defer cancel()
			req, err := http.NewRequestWithContext(
				ctx, http.MethodPost, e.proxy.URL+tn.Path(), strings.NewReader(`{"model":"m"}`),
			)
			if err != nil {
				fail.Add(1)
				return
			}
			req.Header.Set("Content-Type", "application/json")
			req.Header.Set("X-Request-ID", rid)
			req.Header.Set("X-TokenMarket-Project-ID", tn.ProjectID)
			resp, err := http.DefaultClient.Do(req)
			if err != nil {
				fail.Add(1)
				return
			}
			defer resp.Body.Close()
			if resp.StatusCode >= 300 {
				fail.Add(1)
				_ = e.Ledger.Abort(context.Background(), rid)
				return
			}
			_, _ = io.Copy(io.Discard, resp.Body)
			done.Add(1)
			e.Ledger.Settle(rid)
		}(i)
	}
	wg.Wait()
	var endHeap runtime.MemStats
	runtime.GC()
	runtime.ReadMemStats(&endHeap)
	total := n
	disc := float64(fail.Load()) / float64(total)
	rep := Report{
		Profile:          "stream",
		Tenants:          TenantCount,
		Total:            total,
		Success:          int(done.Load()),
		DisconnectRate:   disc,
		HeapDeltaBytes:   int64(endHeap.HeapAlloc) - int64(startHeap.HeapAlloc),
		OpenReservations: e.Ledger.OpenCount(),
		DoubleCharge:     e.Ledger.DoubleCharge,
		CrossTenantLeaks: e.Ledger.Leaks,
	}
	if total > 0 {
		rep.SuccessRate = float64(rep.Success) / float64(total)
	}
	rep.Pass = rep.PassStream()
	return rep
}

func percentile(vals []time.Duration, p float64) time.Duration {
	if len(vals) == 0 {
		return 0
	}
	cp := append([]time.Duration(nil), vals...)
	sort.Slice(cp, func(i, j int) bool { return cp[i] < cp[j] })
	idx := int(float64(len(cp)-1) * p)
	if idx < 0 {
		idx = 0
	}
	return cp[idx]
}

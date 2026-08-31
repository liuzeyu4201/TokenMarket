package capacity

import (
	"fmt"
	"net/http"
	"sync/atomic"
	"time"
)

type MockUpstream struct {
	fail     atomic.Bool
	backlog  atomic.Int64
	delay    atomic.Int64
	hold     atomic.Int64
	requests atomic.Int64
}

func (m *MockUpstream) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	m.requests.Add(1)
	if m.fail.Load() {
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(`{"error":"upstream"}`))
		return
	}
	if n := m.backlog.Load(); n > 0 {
		time.Sleep(time.Duration(n) * time.Millisecond)
	}
	if d := m.delay.Load(); d > 0 {
		time.Sleep(time.Duration(d) * time.Millisecond)
	}
	if h := m.hold.Load(); h > 0 {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		fl, _ := w.(http.Flusher)
		end := time.Now().Add(time.Duration(h))
		for time.Now().Before(end) {
			fmt.Fprint(w, "data: {}\n\n")
			if fl != nil {
				fl.Flush()
			}
			time.Sleep(20 * time.Millisecond)
		}
		return
	}
	path := r.URL.Path
	n := m.requests.Load()
	switch n % 6 {
	case 1:
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, "data: {\"id\":1,\"path\":%q}\n\n", path)
		fmt.Fprint(w, "data: [DONE]\n\n")
	case 2:
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, `{"tool_calls":[{"name":"x"}],"usage":{"total_tokens":8}}`)
	default:
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		fmt.Fprintf(w, `{"ok":true,"echo":%q}`, r.Header.Get("X-TokenMarket-Project-ID"))
	}
}

func (m *MockUpstream) SetFail(v bool) { m.fail.Store(v) }

func (m *MockUpstream) SetBacklog(ms int64) { m.backlog.Store(ms) }

func (m *MockUpstream) SetDelay(ms int64) { m.delay.Store(ms) }

func (m *MockUpstream) SetHold(d time.Duration) { m.hold.Store(int64(d)) }

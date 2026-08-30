package passthrough

import (
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func soakParams() (n int, d time.Duration) {
	n = 8
	d = 200 * time.Millisecond
	if v := strings.TrimSpace(os.Getenv("TOKENMARKET_SOAK_SSE")); v != "" {
		if parsed, err := strconv.Atoi(v); err == nil && parsed > 0 {
			n = parsed
		}
	}
	if v := strings.TrimSpace(os.Getenv("TOKENMARKET_SOAK_DURATION")); v != "" {
		if parsed, err := time.ParseDuration(v); err == nil && parsed > 0 {
			d = parsed
		}
	}
	return n, d
}

func TestSoakConcurrentSSE(t *testing.T) {
	n, dur := soakParams()
	up := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		w.WriteHeader(200)
		fl := w.(http.Flusher)
		deadline := time.Now().Add(dur)
		seq := 0
		for time.Now().Before(deadline) {
			fmt.Fprintf(w, "data: %d\n\n", seq)
			fl.Flush()
			seq++
			time.Sleep(20 * time.Millisecond)
		}
	}))
	t.Cleanup(up.Close)
	k := &Kernel{
		Catalog:  testCatalog(),
		Selector: StaticSelector{Up: Upstream{BaseURL: up.URL, Credential: "k"}},
		Limits:   Limits{IdleTimeout: time.Second, UpstreamTimeout: dur + time.Second},
	}
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		k.ServeHTTP(w, r, "shared", false)
	}))
	t.Cleanup(proxy.Close)

	var wg sync.WaitGroup
	var fail atomic.Int32
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			ctxReq, err := http.NewRequest(http.MethodPost, proxy.URL+"/openai/v1/chat/completions", strings.NewReader(`{"model":"m"}`))
			if err != nil {
				fail.Add(1)
				return
			}
			resp, err := http.DefaultClient.Do(ctxReq)
			if err != nil {
				fail.Add(1)
				return
			}
			defer resp.Body.Close()
			prev := -1
			buf := make([]byte, 0, 256)
			tmp := make([]byte, 64)
			for {
				nread, rerr := resp.Body.Read(tmp)
				if nread > 0 {
					buf = append(buf, tmp[:nread]...)
					for {
						i := strings.Index(string(buf), "\n\n")
						if i < 0 {
							break
						}
						ev := string(buf[:i])
						buf = buf[i+2:]
						var seq int
						if _, err := fmt.Sscanf(ev, "data: %d", &seq); err == nil {
							if prev >= 0 && seq != prev+1 {
								fail.Add(1)
								return
							}
							prev = seq
						}
					}
				}
				if rerr != nil {
					if rerr != io.EOF && fail.Load() == 0 && prev < 0 {
						fail.Add(1)
					}
					return
				}
			}
		}()
	}
	wg.Wait()
	if fail.Load() != 0 {
		t.Fatalf("soak failures %d (n=%d dur=%s)", fail.Load(), n, dur)
	}
}

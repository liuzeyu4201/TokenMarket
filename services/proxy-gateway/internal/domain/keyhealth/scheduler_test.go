package keyhealth_test

import (
	"context"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/keyhealth"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/providervalid"
)

type memStore struct {
	keys []keyhealth.KeyFact
}

func (m *memStore) ListActive(context.Context) []keyhealth.KeyFact { return m.keys }
func (m *memStore) ApplyHealth(_ context.Context, id, health string) error {
	for i := range m.keys {
		if m.keys[i].ID == id {
			m.keys[i].Health = health
		}
	}
	return nil
}

func TestTickUpdatesFromProbe(t *testing.T) {
	st := &memStore{keys: []keyhealth.KeyFact{
		{ID: "a", APIKey: "k", Health: "unknown", Admin: "active"},
		{ID: "b", APIKey: "k2", Health: "unknown", Admin: "paused"},
	}}
	sch := &keyhealth.Scheduler{
		Store: st,
		Probe: func(ctx context.Context, apiKey string) providervalid.ErrorCategory {
			if apiKey == "k" {
				return providervalid.CategorySuccess
			}
			return providervalid.CategoryInvalid
		},
	}
	n := sch.Tick(context.Background())
	if n != 1 {
		t.Fatalf("updated %d", n)
	}
	if st.keys[0].Health != "healthy" {
		t.Fatal(st.keys[0].Health)
	}
	if st.keys[1].Health != "unknown" {
		t.Fatal("paused should skip")
	}
}

func TestTickInvokesOnProbeForActiveKeys(t *testing.T) {
	st := &memStore{keys: []keyhealth.KeyFact{
		{ID: "a", APIKey: "k", Health: "unknown", Admin: "active"},
		{ID: "b", APIKey: "k2", Health: "unknown", Admin: "paused"},
	}}
	var saw []string
	sch := &keyhealth.Scheduler{
		Store: st,
		Probe: func(context.Context, string) providervalid.ErrorCategory {
			return providervalid.CategorySuccess
		},
		OnProbe: func(platform, result string) {
			saw = append(saw, platform+"/"+result)
		},
	}
	sch.Tick(context.Background())
	if len(saw) != 1 || saw[0] != "volcano/success" {
		t.Fatalf("%v", saw)
	}
}

func TestInvalidNotOverwrittenByTransient(t *testing.T) {
	if keyhealth.NextHealth("invalid", providervalid.CategoryTimeout) != "invalid" {
		t.Fatal("transient must not clear invalid")
	}
	if keyhealth.NextHealth("invalid", providervalid.CategorySuccess) != "healthy" {
		t.Fatal("success may recover")
	}
}

func TestThreeTemporaryFailuresMarkDown(t *testing.T) {
	st := &memStore{keys: []keyhealth.KeyFact{
		{ID: "a", APIKey: "k", Health: "healthy", Admin: "active"},
	}}
	n := 0
	sch := &keyhealth.Scheduler{
		Store: st,
		Probe: func(context.Context, string) providervalid.ErrorCategory {
			n++
			return providervalid.CategoryTimeout
		},
	}
	sch.Tick(context.Background())
	if st.keys[0].Health != "healthy" {
		t.Fatalf("first temp must keep healthy, got %s", st.keys[0].Health)
	}
	sch.Tick(context.Background())
	if st.keys[0].Health != "healthy" {
		t.Fatalf("second temp must keep healthy, got %s", st.keys[0].Health)
	}
	sch.Tick(context.Background())
	if st.keys[0].Health != "down" {
		t.Fatalf("third temp must down, got %s", st.keys[0].Health)
	}
	if n != 3 {
		t.Fatalf("probes %d", n)
	}
}

func TestSuccessClearsTemporaryStrikes(t *testing.T) {
	st := &memStore{keys: []keyhealth.KeyFact{
		{ID: "a", APIKey: "k", Health: "healthy", Admin: "active"},
	}}
	cats := []providervalid.ErrorCategory{
		providervalid.CategoryTimeout,
		providervalid.CategorySuccess,
		providervalid.CategoryTimeout,
	}
	i := 0
	sch := &keyhealth.Scheduler{
		Store: st,
		Probe: func(context.Context, string) providervalid.ErrorCategory {
			c := cats[i]
			i++
			return c
		},
	}
	sch.Tick(context.Background())
	sch.Tick(context.Background())
	sch.Tick(context.Background())
	if st.keys[0].Health != "healthy" {
		t.Fatalf("success must reset strikes, got %s", st.keys[0].Health)
	}
}

func TestRateLimitedSkipsUntilNextCheck(t *testing.T) {
	st := &memStore{keys: []keyhealth.KeyFact{
		{ID: "a", APIKey: "k", Health: "healthy", Admin: "active"},
	}}
	probes := 0
	now := time.Date(2026, 8, 25, 12, 0, 0, 0, time.UTC)
	sch := &keyhealth.Scheduler{
		Store: st,
		Now:   func() time.Time { return now },
		Probe: func(context.Context, string) providervalid.ErrorCategory {
			probes++
			return providervalid.CategoryRateLimited
		},
	}
	sch.Tick(context.Background())
	if st.keys[0].Health != "rate_limited" {
		t.Fatal(st.keys[0].Health)
	}
	now = now.Add(29 * time.Minute)
	sch.Tick(context.Background())
	if probes != 1 {
		t.Fatalf("should skip until 30m, probes=%d", probes)
	}
	now = now.Add(2 * time.Minute)
	sch.Tick(context.Background())
	if probes != 2 {
		t.Fatalf("should probe after 30m, probes=%d", probes)
	}
}

func TestRunStopsOnCancel(t *testing.T) {
	st := &memStore{keys: []keyhealth.KeyFact{{ID: "a", APIKey: "k", Health: "unknown", Admin: "active"}}}
	sch := &keyhealth.Scheduler{
		Interval: 20 * time.Millisecond,
		Store:    st,
		Probe:    func(context.Context, string) providervalid.ErrorCategory { return providervalid.CategoryRateLimited },
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		sch.Run(ctx)
		close(done)
	}()
	time.Sleep(50 * time.Millisecond)
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("scheduler did not stop")
	}
	if st.keys[0].Health != "rate_limited" {
		t.Fatal(st.keys[0].Health)
	}
}

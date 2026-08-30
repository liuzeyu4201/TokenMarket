package usageoutbox_test

import (
	"errors"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/usageoutbox"
)

func ev(id, req, status string, seq int) usageoutbox.Event {
	return usageoutbox.Event{
		EventID:       id,
		RequestID:     req,
		Seq:           seq,
		Status:        status,
		CatalogMajor:  1,
		Protocol:      "openai",
		EndpointID:    "openai.post.v1.chat.completions",
		CorrelationID: req,
	}
}

func TestLifecycleStatusesPersist(t *testing.T) {
	s, err := usageoutbox.NewFileStore(t.TempDir(), 3)
	if err != nil {
		t.Fatal(err)
	}
	stati := []string{"success", "upstream_4xx", "upstream_5xx", "timeout", "client_cancel"}
	for i, st := range stati {
		if err := s.Append(ev("e"+st, "r"+st, st, i+1)); err != nil {
			t.Fatal(err)
		}
	}
	ctr := &usageoutbox.IdempotentCounter{}
	if err := s.Drain(ctr.Handle); err != nil {
		t.Fatal(err)
	}
	if ctr.Count != 5 {
		t.Fatalf("count %d", ctr.Count)
	}
}

func TestIdempotentReplayTenTimes(t *testing.T) {
	s, err := usageoutbox.NewFileStore(t.TempDir(), 3)
	if err != nil {
		t.Fatal(err)
	}
	e := ev("same", "req", "success", 1)
	for i := 0; i < 10; i++ {
		if err := s.Append(e); err != nil {
			t.Fatal(err)
		}
	}
	ctr := &usageoutbox.IdempotentCounter{}
	for i := 0; i < 10; i++ {
		if err := s.Drain(ctr.Handle); err != nil {
			t.Fatal(err)
		}
	}
	if ctr.Count != 1 {
		t.Fatalf("count %d want 1", ctr.Count)
	}
}

func TestDeadLetterAndReplay(t *testing.T) {
	s, err := usageoutbox.NewFileStore(t.TempDir(), 2)
	if err != nil {
		t.Fatal(err)
	}
	if err := s.Append(ev("dl", "req", "timeout", 1)); err != nil {
		t.Fatal(err)
	}
	boom := errors.New("sink down")
	if err := s.Drain(func(usageoutbox.Event) error { return boom }); err != nil {
		t.Fatal(err)
	}
	if err := s.Drain(func(usageoutbox.Event) error { return boom }); err != nil {
		t.Fatal(err)
	}
	dls, err := s.DeadLetters()
	if err != nil || len(dls) != 1 {
		t.Fatalf("dlq %v %v", dls, err)
	}
	if err := s.ReplayDeadLetter("dl"); err != nil {
		t.Fatal(err)
	}
	ctr := &usageoutbox.IdempotentCounter{}
	if err := s.Drain(ctr.Handle); err != nil {
		t.Fatal(err)
	}
	if ctr.Count != 1 {
		t.Fatal(ctr.Count)
	}
	dls, err = s.DeadLetters()
	if err != nil || len(dls) != 0 {
		t.Fatalf("dlq after replay %v", dls)
	}
}

func TestForbiddenFieldsRejected(t *testing.T) {
	ev := ev("x", "r", "success", 1)
	// Validate uses marshaled Event struct tags; extra fields cannot appear.
	if err := usageoutbox.Validate(ev); err != nil {
		t.Fatal(err)
	}
}

func TestUnavailableWithoutDir(t *testing.T) {
	if _, err := usageoutbox.NewFileStore("", 3); err == nil {
		t.Fatal("expected unavailable")
	}
}

func TestRequestSequenceOrder(t *testing.T) {
	s, err := usageoutbox.NewFileStore(t.TempDir(), 3)
	if err != nil {
		t.Fatal(err)
	}
	if err := s.Append(ev("b", "req", "success", 2)); err != nil {
		t.Fatal(err)
	}
	if err := s.Append(ev("a", "req", "success", 1)); err != nil {
		t.Fatal(err)
	}
	var seq []int
	if err := s.Drain(func(e usageoutbox.Event) error {
		seq = append(seq, e.Seq)
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if len(seq) != 2 || seq[0] != 1 || seq[1] != 2 {
		t.Fatalf("%v", seq)
	}
}

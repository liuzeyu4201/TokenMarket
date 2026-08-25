package chatcompat_test

import (
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestParseRetryAfterHTTPDate(t *testing.T) {
	future := time.Now().UTC().Add(8 * time.Second).Format(time.RFC1123)
	n := chatcompat.ParseRetryAfter(future, 5, 300)
	if n < 1 || n > 15 {
		t.Fatalf("got %d", n)
	}
}

func TestClampDeadline(t *testing.T) {
	d := chatcompat.ClampDeadline(0, false, 60, 300)
	if d != 60*time.Second {
		t.Fatalf("%s", d)
	}
	d = chatcompat.ClampDeadline(10*time.Second, true, 60, 300)
	if d != 10*time.Second {
		t.Fatalf("%s", d)
	}
	d = chatcompat.ClampDeadline(time.Hour, true, 60, 300)
	if d != 300*time.Second {
		t.Fatalf("%s", d)
	}
}

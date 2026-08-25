package application_test

import (
	"context"
	"encoding/json"
	"testing"
	"time"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestDefaultDeadlineTimeout(t *testing.T) {
	cfg := chatTestCfg()
	cfg.DefaultDeadlineSec = 1
	st := &stubPoster{block: 3 * time.Second}
	svc := &application.ChatService{Cfg: cfg, Client: st}
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	start := time.Now()
	got, _ := svc.Complete(context.Background(), req)
	if time.Since(start) > 2500*time.Millisecond {
		t.Fatalf("too long")
	}
	if got.ErrorCategory != chatcompat.CategoryTimeout {
		t.Fatalf("%s", got.ErrorCategory)
	}
}

func TestCallerShorterDeadlineWins(t *testing.T) {
	cfg := chatTestCfg()
	cfg.DefaultDeadlineSec = 60
	st := &stubPoster{block: 5 * time.Second}
	svc := &application.ChatService{Cfg: cfg, Client: st}
	ctx, cancel := context.WithTimeout(context.Background(), 80*time.Millisecond)
	defer cancel()
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	start := time.Now()
	got, _ := svc.Complete(ctx, req)
	if time.Since(start) > 2*time.Second {
		t.Fatal("did not honor caller")
	}
	if got.ErrorCategory != chatcompat.CategoryTimeout {
		t.Fatalf("%s", got.ErrorCategory)
	}
}

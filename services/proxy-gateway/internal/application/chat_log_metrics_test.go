package application_test

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/observability"
)

func TestCompleteLogHasNoKeyOrMessageBody(t *testing.T) {
	var buf bytes.Buffer
	log := slog.New(slog.NewTextHandler(&buf, nil))
	body := []byte(`{"id":"1","choices":[{"index":0,"message":{"role":"assistant","content":"secret-user-text"},"finish_reason":"stop"}]}`)
	st := &stubPoster{status: 200, body: body}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st, Logger: log, Metrics: observability.NewChatMetrics()}
	key := "sk-synthetic-test-key-not-real"
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: key, RequestID: "r1", Model: "doubao-pro-32k",
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"secret-user-text"`)}},
	}
	_, _ = svc.Complete(context.Background(), req)
	out := buf.String()
	if chatcompat.ContainsSecret(out, key) {
		t.Fatal(out)
	}
	if bytes.Contains([]byte(out), []byte("secret-user-text")) {
		t.Fatal(out)
	}
}

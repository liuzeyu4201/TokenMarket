package application_test

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

func TestStreamZeroEvent401StructuredInvalid(t *testing.T) {
	st := &stubPoster{status: 401, body: []byte(`{"error":"no"}`)}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	tr := true
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k", Stream: &tr,
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	var evs []chatcompat.StreamEvent
	for ev := range svc.Stream(context.Background(), req) {
		evs = append(evs, ev)
	}
	if len(evs) != 1 {
		t.Fatalf("%+v", evs)
	}
	if evs[0].Kind != chatcompat.KindError || evs[0].ErrorCategory != chatcompat.CategoryInvalid {
		t.Fatalf("%+v", evs[0])
	}
	if evs[0].Kind == chatcompat.KindDone {
		t.Fatal("done")
	}
}

func TestStreamTruncatedAfterDeltaNoDone(t *testing.T) {
	payload := "data: {\"choices\":[{\"delta\":{\"content\":\"a\"}}]}\n\n"
	st := &stubPoster{status: 200, stream: staticRC{strings.NewReader(payload)}}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	tr := true
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k", Stream: &tr,
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	var evs []chatcompat.StreamEvent
	for ev := range svc.Stream(context.Background(), req) {
		evs = append(evs, ev)
	}
	var sawTrunc, sawDone bool
	for _, e := range evs {
		if e.Kind == chatcompat.KindTruncated {
			sawTrunc = true
			if e.ErrorCategory != chatcompat.CategoryTruncatedStream {
				t.Fatalf("%s", e.ErrorCategory)
			}
		}
		if e.Kind == chatcompat.KindDone {
			sawDone = true
		}
	}
	if !sawTrunc || sawDone {
		t.Fatalf("%+v", evs)
	}
}

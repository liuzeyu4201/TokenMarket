package application_test

import (
	"context"
	"encoding/json"
	"io"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/application"
	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/chatcompat"
)

type staticRC struct{ *strings.Reader }

func (s staticRC) Close() error { return nil }

func TestStreamDeltaOrderAndSingleDone(t *testing.T) {
	payload := "data: {\"id\":\"c1\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"a\"}}]}\n\n" +
		"data: {\"id\":\"c1\",\"choices\":[{\"index\":0,\"delta\":{\"content\":\"b\"}}]}\n\n" +
		"data: [DONE]\n\n"
	st := &stubPoster{status: 200, stream: staticRC{strings.NewReader(payload)}}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	tr := true
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k", Stream: &tr,
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	var kinds []chatcompat.StreamKind
	for ev := range svc.Stream(context.Background(), req) {
		kinds = append(kinds, ev.Kind)
	}
	if len(kinds) < 3 {
		t.Fatalf("%v", kinds)
	}
	done := 0
	for _, k := range kinds {
		if k == chatcompat.KindDone {
			done++
		}
	}
	if done != 1 {
		t.Fatalf("done=%d %v", done, kinds)
	}
	if kinds[0] != chatcompat.KindDelta || kinds[1] != chatcompat.KindDelta {
		t.Fatalf("order %v", kinds)
	}
}

func TestStreamUnsupportedParameterNoUpstream(t *testing.T) {
	st := &stubPoster{}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	tr := true
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "nope", Stream: &tr,
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	var evs []chatcompat.StreamEvent
	for ev := range svc.Stream(context.Background(), req) {
		evs = append(evs, ev)
	}
	if len(evs) != 1 || evs[0].Kind != chatcompat.KindError || evs[0].ErrorCategory != chatcompat.CategoryUnsupportedParameter {
		t.Fatalf("%+v", evs)
	}
	if st.n.Load() != 0 {
		t.Fatal("upstream")
	}
}

func TestStreamTransportError(t *testing.T) {
	st := &stubPoster{err: context.DeadlineExceeded}
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
	if len(evs) != 1 || evs[0].Kind != chatcompat.KindError {
		t.Fatalf("%+v", evs)
	}
}

func TestStreamDoneWithoutUsage(t *testing.T) {
	payload := "data: {\"choices\":[{\"delta\":{\"content\":\"z\"}}]}\n\ndata: [DONE]\n\n"
	st := &stubPoster{status: 200, stream: staticRC{strings.NewReader(payload)}}
	svc := &application.ChatService{Cfg: chatTestCfg(), Client: st}
	tr := true
	req := chatcompat.ChatAdaptRequest{
		Platform: "volcano", APIKey: "sk-synthetic-test-key-not-real", Model: "doubao-pro-32k", Stream: &tr,
		Messages: []chatcompat.ChatMessage{{Role: "user", Content: json.RawMessage(`"hi"`)}},
	}
	var last chatcompat.StreamEvent
	for ev := range svc.Stream(context.Background(), req) {
		last = ev
	}
	if last.Kind != chatcompat.KindDone {
		t.Fatalf("%s", last.Kind)
	}
	_ = io.EOF
}

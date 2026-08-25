package volcano_test

import (
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

func TestSSEIncompleteUTF8AcrossChunks(t *testing.T) {
	// "你好" UTF-8 is e4 bda0 e5 a5 bd — split mid-rune
	full := "data: {\"c\":\"你好\"}\n\n"
	b := []byte(full)
	split := 10
	if split >= len(b) {
		split = len(b) / 2
	}
	r := &chunkReader{parts: []string{string(b[:split]), string(b[split:])}}
	p := volcano.NewSSEParser(r)
	ev, err := p.Next()
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(ev.Data, "你好") {
		t.Fatalf("corrupted %q", ev.Data)
	}
}

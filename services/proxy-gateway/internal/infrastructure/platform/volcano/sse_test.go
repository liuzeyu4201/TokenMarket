package volcano_test

import (
	"io"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

type chunkReader struct {
	parts []string
	i     int
}

func (c *chunkReader) Read(p []byte) (int, error) {
	if c.i >= len(c.parts) {
		return 0, io.EOF
	}
	n := copy(p, c.parts[c.i])
	c.i++
	return n, nil
}

func TestSSESplitAcrossWrites(t *testing.T) {
	r := &chunkReader{parts: []string{"data: {\"id\":\"a\"", "}\n\n"}}
	p := volcano.NewSSEParser(r)
	ev, err := p.Next()
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(ev.Data, `"id":"a"`) {
		t.Fatalf("data %q", ev.Data)
	}
}

func TestSSETwoEventsOneWrite(t *testing.T) {
	r := strings.NewReader("data: {\"n\":1}\n\ndata: {\"n\":2}\n\n")
	p := volcano.NewSSEParser(r)
	a, err := p.Next()
	if err != nil {
		t.Fatal(err)
	}
	b, err := p.Next()
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(a.Data, `"n":1`) || !strings.Contains(b.Data, `"n":2`) {
		t.Fatalf("%q %q", a.Data, b.Data)
	}
}

func TestSSECommentsMultilineDataUnknownEvent(t *testing.T) {
	raw := ": ping\n\nevent: ignore\ndata: hello\ndata: world\n\n"
	p := volcano.NewSSEParser(strings.NewReader(raw))
	ev, err := p.Next()
	if err != nil {
		t.Fatal(err)
	}
	if ev.Data != "hello\nworld" {
		t.Fatalf("got %q", ev.Data)
	}
}

func TestSSEParserIsIncremental(t *testing.T) {
	p := volcano.NewSSEParser(strings.NewReader("data: x\n\n"))
	if !p.Incremental() {
		t.Fatal("must be incremental")
	}
}

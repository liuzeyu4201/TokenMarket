package volcano_test

import (
	"bytes"
	"fmt"
	"io"
	"strings"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

func TestSSEScaleTenThousandEvents(t *testing.T) {
	const n = 10000
	var buf bytes.Buffer
	buf.Grow(n * 48)
	for i := 0; i < n; i++ {
		switch i % 5 {
		case 0:
			fmt.Fprintf(&buf, "data: {\"i\":%d}\n\n", i)
		case 1:
			fmt.Fprintf(&buf, ": cmt\ndata: {\"i\":%d}\n\n", i)
		case 2:
			// 合包：本循环仍一事一事件；拆包在 reader 侧
			fmt.Fprintf(&buf, "data: {\"i\":%d}\n\n", i)
		case 3:
			fmt.Fprintf(&buf, "data: {\"i\":\ndata: %d}\n\n", i)
		default:
			fmt.Fprintf(&buf, "event: x\ndata: {\"i\":%d}\n\n", i)
		}
	}
	buf.WriteString("data: [DONE]\n\n")

	// 拆包：不规则块
	raw := buf.Bytes()
	var parts []string
	for i := 0; i < len(raw); {
		sz := 17 + (i % 31)
		if i+sz > len(raw) {
			sz = len(raw) - i
		}
		parts = append(parts, string(raw[i:i+sz]))
		i += sz
	}
	p := volcano.NewSSEParser(&chunkReader{parts: parts})
	var ids []int
	done := 0
	for {
		ev, err := p.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if volcano.IsDoneData(ev.Data) {
			done++
			continue
		}
		var i int
		if _, err := fmt.Sscanf(strings.ReplaceAll(ev.Data, "\n", ""), `{"i":%d}`, &i); err != nil {
			t.Fatalf("parse %q: %v", ev.Data, err)
		}
		ids = append(ids, i)
	}
	if len(ids) != n {
		t.Fatalf("got %d want %d", len(ids), n)
	}
	seen := map[int]int{}
	for i, v := range ids {
		if v != i {
			t.Fatalf("order at %d got %d", i, v)
		}
		seen[v]++
		if seen[v] > 1 {
			t.Fatalf("dup %d", v)
		}
	}
	if done != 1 {
		t.Fatalf("done=%d", done)
	}
}

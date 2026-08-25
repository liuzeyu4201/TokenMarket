package volcano_test

import (
	"io"
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/infrastructure/platform/volcano"
)

func FuzzSSEParser(f *testing.F) {
	f.Add([]byte("data: {}\n\n"))
	f.Add([]byte(":c\n\ndata: [DONE]\n\n"))
	f.Add([]byte{0xff, 0xfe, '\n', '\n'})
	f.Fuzz(func(t *testing.T, in []byte) {
		p := volcano.NewSSEParser(bytesReader(in))
		for i := 0; i < 64; i++ {
			_, err := p.Next()
			if err != nil {
				if err == io.EOF || err == io.ErrUnexpectedEOF {
					return
				}
				return
			}
		}
	})
}

type bytesR struct{ b []byte }

func bytesReader(b []byte) *bytesR { return &bytesR{b: b} }

func (r *bytesR) Read(p []byte) (int, error) {
	if len(r.b) == 0 {
		return 0, io.EOF
	}
	n := copy(p, r.b)
	r.b = r.b[n:]
	return n, nil
}

package endpcatalog_test

import (
	"testing"

	"github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"
)

func BenchmarkAdmitFullCatalog(b *testing.B) {
	c, err := endpcatalog.LoadEmbedded(1)
	if err != nil {
		b.Fatal(err)
	}
	in := endpcatalog.AdmitInput{
		Provider:    "openai",
		Method:      "POST",
		Path:        "/v1/chat/completions",
		ProjectMode: "shared",
	}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		d := endpcatalog.Admit(c, in)
		if !d.Allow {
			b.Fatal(d.Code)
		}
	}
}

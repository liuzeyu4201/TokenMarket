package capacity

import "github.com/tokenmarket/tokenmarket/services/proxy-gateway/internal/domain/endpcatalog"

func Catalog() *endpcatalog.Catalog {
	return &endpcatalog.Catalog{
		CatalogMajor: 1,
		Providers:    []string{"openai", "anthropic", "vertex"},
		Records: []endpcatalog.EndpointRecord{
			{
				ID:           "openai.post.v1.chat.completions",
				Provider:     "openai",
				Method:       "POST",
				PathTemplate: "/v1/chat/completions",
				Stability:    "stable",
				Transport:    "sse",
			},
			{
				ID:           "anthropic.post.v1.messages",
				Provider:     "anthropic",
				Method:       "POST",
				PathTemplate: "/v1/messages",
				Stability:    "stable",
				Transport:    "sse",
			},
			{
				ID:           "vertex.post.generate",
				Provider:     "vertex",
				Method:       "POST",
				PathTemplate: "/v1/projects/{project}/locations/{location}/publishers/{publisher}/models/{model}:generateContent",
				Stability:    "stable",
			},
		},
	}
}

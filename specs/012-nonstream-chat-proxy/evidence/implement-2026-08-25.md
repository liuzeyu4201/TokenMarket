# Implement 2026-08-25

Public `POST /v1/proxy/volcano/chat/completions` mounted from `cmd/gateway` when `PROXY_ENABLED≠0`.

Pre-stream failures use `{code,message,data,request_id,timestamp}`. Success body is OpenAI-shaped.
`rate_limited` → HTTP 429; schema → 400; auth → 401; timeout → 504; other upstream → 502.

httptest: `internal/httpserver/proxy_test.go`.

# Implement 2026-08-25

`OpenStream` returns pre-stream `*ChatAdaptResult` for JSON envelope. After upstream 200, handler writes OpenAI `chat.completion.chunk` SSE and `data: [DONE]`. Internal `kind` is not serialized.

httptest: `TestProxySSEOpenAIChunks`, `TestProxyStreamUpstream401BeforeSSE`.

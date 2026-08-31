"""Native same-protocol developer samples. No cross-protocol conversion."""

from __future__ import annotations

SAMPLES: dict[str, dict[str, str]] = {
    "openai": {
        "curl": (
            "curl https://api.tokenmarket.local/openai/v1/chat/completions "
            "-H 'Authorization: Bearer $TOKENMARKET_KEY' "
            "-H 'Content-Type: application/json' "
            '-d \'{"model":"gpt-test","messages":[{"role":"user","content":"hi"}]}\''
        ),
        "sdk": (
            "from openai import OpenAI\n"
            "client = OpenAI(api_key=os.environ['TOKENMARKET_KEY'], "
            "base_url='https://api.tokenmarket.local/openai/v1')\n"
            "client.chat.completions.create("
            "model='gpt-test', messages=[{'role':'user','content':'hi'}])"
        ),
        "auth_header": "Authorization: Bearer",
        "path": "/openai/v1/chat/completions",
    },
    "anthropic": {
        "curl": (
            "curl https://api.tokenmarket.local/anthropic/v1/messages "
            "-H 'x-api-key: $TOKENMARKET_KEY' "
            "-H 'anthropic-version: 2023-06-01' "
            "-H 'Content-Type: application/json' "
            '-d \'{"model":"claude-test","max_tokens":32,'
            '"messages":[{"role":"user","content":"hi"}]}\''
        ),
        "sdk": (
            "from anthropic import Anthropic\n"
            "client = Anthropic(api_key=os.environ['TOKENMARKET_KEY'], "
            "base_url='https://api.tokenmarket.local/anthropic')\n"
            "client.messages.create(model='claude-test', max_tokens=32, "
            "messages=[{'role':'user','content':'hi'}])"
        ),
        "auth_header": "x-api-key",
        "path": "/anthropic/v1/messages",
    },
    "vertex": {
        "curl": (
            "curl https://api.tokenmarket.local/vertex/v1/projects/p/locations/us/"
            "publishers/google/models/gemini-test:generateContent "
            "-H 'Authorization: Bearer $TOKENMARKET_KEY' "
            "-H 'Content-Type: application/json' "
            '-d \'{"contents":[{"role":"user","parts":[{"text":"hi"}]}]}\''
        ),
        "sdk": (
            "import google.auth.transport.requests\n"
            "# Vertex generateContent via native path; no OpenAI chat conversion.\n"
            "url = 'https://api.tokenmarket.local/vertex/v1/projects/p/locations/us/"
            "publishers/google/models/gemini-test:generateContent'"
        ),
        "auth_header": "Authorization: Bearer",
        "path": ":generateContent",
    },
}

CHECKLIST = (
    ("binding", "发布 Provider Binding"),
    ("key", "签发 Project 代理 Key"),
    ("sample", "用原生示例发出测试请求"),
    ("result", "查看用量与测试额度结果"),
)

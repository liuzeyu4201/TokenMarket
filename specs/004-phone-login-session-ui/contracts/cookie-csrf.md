# Contract：Browser Session Cookie、CSRF 与 Origin v1

## Session Cookie

| Attribute | Required value |
|-----------|----------------|
| Name | `__Host-tokenmarket_session` |
| Value | `<key-version>.<opaque-secret>`；至少 256-bit CSPRNG secret |
| `Secure` | always |
| `HttpOnly` | always |
| `SameSite` | `Lax` |
| `Path` | `/` |
| `Domain` | absent |
| `Max-Age` | `3600` on issue; `0` on clear |
| `Expires` | server expiry on issue; past time on clear |

- Issue only after challenge-consume/session-insert transaction commits。
- Clear uses the exact same Name/Path/Domain/Secure/HttpOnly/SameSite scope。
- Rotate on every successful login; never accept a caller-supplied session identifier。
- Never copy Cookie or Set-Cookie into response body, logs, metrics, traces, analytics, URLs or
  Frontend storage。
- Every auth/session response sets `Cache-Control: no-store`。

## CSRF token

- Server computes a deterministic, versioned HMAC bound to the current `session_id`。
- Login success and `GET /api/v1/auth/session` return it as `data.csrf_token`。
- It is not an authentication credential and cannot identify another session。
- Frontend keeps it in memory only; no localStorage/sessionStorage/URL/logging。
- Cookie-authenticated unsafe methods require `X-CSRF-Token` and constant-time verification。
- Session replacement/expiry/revoke makes the old CSRF token invalid automatically。

## Origin policy

- Browser write endpoints require exact `Origin` allowlist match。
- If a supported non-browser context omits Origin, it needs an explicit reviewed caller policy；
  it must not silently enter the browser path。
- `Origin: null`, malformed origins, wildcard matching and suffix/string contains matching are
  rejected。
- Strict Referer fallback is allowed only when Origin is legitimately absent and must compare
  scheme + host + effective port。
- Verification request/session creation also check Origin to prevent login-CSRF。

## Same-origin topology

### Local

```text
Browser ── HTTPS ──> Vite :5173
                       ├── SPA assets/routes
                       └── /api/* proxy ── HTTP loopback ──> API Service :8000
```

Vite uses a generated local self-signed certificate from a locked development plugin. No
certificate key is committed. Root workflow probes know this exact local endpoint and do not
disable certificate verification globally。

### Test / production

```text
Browser ── HTTPS trusted edge ──> Frontend Nginx
                                     ├── SPA assets/routes
                                     └── /api/* ── private app network ──> API Service
```

Production activation is blocked without TLS edge facts and trusted proxy/origin configuration。
Internal container health checks may remain HTTP loopback because they do not carry user traffic。

## CORS fallback

Same-origin is the default. If a reviewed test topology is cross-origin:

- exact origins only；
- `allow_credentials=true`；
- methods: `GET`, `POST`, `DELETE`, `OPTIONS`；
- request headers: `Content-Type`, `X-Request-ID`, `Idempotency-Key`, `X-CSRF-Token`；
- exposed response header: `X-Request-ID`；
- no `*` for origin/method/header on credentialed routes。

## Validation evidence

- Set-Cookie issue/clear attribute equality；
- JavaScript cannot read session Cookie；
- refresh can bootstrap session and receive a CSRF token；
- missing/wrong/cross-session CSRF → 403 and no state change；
- malicious/null Origin → 403；
- allowed same-origin preflight/request succeeds；
- old device Cookie fails within 1 second after new login；
- response/log/metric scan finds no Cookie, token or CSRF value。


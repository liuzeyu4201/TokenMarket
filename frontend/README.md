# Frontend

TokenMarket React 18 web frontend (SF01 scaffold + registration shell for SF03).

## Ownership

- Owner: TokenMarket Engineering
- Type: React web frontend

## Commands

```bash
make bootstrap
make fmt
make type-check
make lint
make test
make build
```

## Routes

| Path        | Purpose                                  |
| ----------- | ---------------------------------------- |
| `/`         | Home placeholder (not the register form) |
| `/register` | User registration form                   |
| `*`         | Not found / not yet open                 |

## Local development

```bash
# optional: point at local API Service
# echo 'VITE_API_BASE_URL=http://127.0.0.1:8000' > .env.development
npm run dev
```

- Register requests use a **10s** timeout and **do not auto-retry**; manual retry reuses the same `Idempotency-Key`.
- **Manual ER-004 check**: after a cold `npm run dev`, open `/register` and confirm the form is interactive within **3 seconds** on a typical machine (not a CI gate).
- Registration does not log the user in (no tokens).

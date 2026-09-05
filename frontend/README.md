# Frontend

TokenMarket React web app: unified buyer/seller workspace plus an isolated `/admin` shell.

Hub: [`docs/architecture/README.md`](../docs/architecture/README.md) · [English](../docs/architecture/README.en.md).

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

| Path                   | Purpose                                    |
| ---------------------- | ------------------------------------------ |
| `/`                    | Home (product boundary copy)               |
| `/register`            | Phone OTP register                         |
| `/login`               | Phone OTP login                            |
| `/projects`            | Buyer Projects (session)                   |
| `/projects/:projectId` | Project detail, bindings, keys             |
| `/connections`         | Seller Provider Connections (no plaintext) |
| `/supply`              | Seller supply / quotes                     |
| `/account/security`    | Session security                           |
| `/dashboard`           | Authenticated landing                      |
| `/admin/login`         | Isolated admin login (not buyer cookie)    |
| `/admin`               | Ops catalog / publish / wizards            |
| `*`                    | Not found                                  |

Daily local run is `make start` from the repo root (Vite on `:5173`). Direct `npm run dev` is maintenance only.

- Register/login use a **10s** timeout and **do not auto-retry**.
- Do not log phone numbers, OTP codes, or Connection secrets.

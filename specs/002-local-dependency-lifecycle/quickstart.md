# Quickstart Validation: 本地依赖环境生命周期

**Feature**: `002-local-dependency-lifecycle`
**Purpose**: Post-implementation acceptance guide; automated tests remain authoritative for destructive, concurrent, and fault-injection cases
**Safety**: Use only synthetic local credentials and data. Never point these commands at test/production resources.

## 1. Verify the maintained host toolchain

From the repository root:

```bash
make help
make toolchain-check
```

Expected:

- Help still lists `make dev` and `make dev-down` as the only public local dependency lifecycle actions and explains side effects/recovery.
- Docker 29.5.3 and Compose 5.1.4 are validated without installation or upgrade.
- The daemon is a reachable local Linux-container endpoint on macOS arm64 or Linux x86_64; remote contexts fail before configuration/resource access.
- No output contains environment values or an absolute workspace path.
- Docker/Compose labels contain only the safe runtime project directory where Compose requires a path; neither the raw nor canonical workspace path appears in any label.

If Docker Desktop/Engine is stopped or the current user lacks access, fix that outside the repository and rerun. The workflow must not invoke `sudo`, change groups, or start a system service.

## 2. Prepare ignored synthetic local configuration

```bash
cp .env.example .env.local
git check-ignore .env.local
python3 -c 'import secrets; print("tm_local_" + secrets.token_urlsafe(24))'
```

Use independently generated values for every SF02 password placeholder. Each decoded value must start with `tm_local_` and contain 32–96 URL-safe characters after the prefix. Set the fields to this shape:

```text
MODE=local
DATABASE_URL=postgresql://<local-user>:tm_local_<32-96-url-safe-chars>@127.0.0.1:5432/<local-database>
REDIS_URL=redis://default:tm_local_<different-32-96-url-safe-chars>@127.0.0.1:6379/0
GRAFANA_URL=http://127.0.0.1:3000
GRAFANA_ADMIN_PASSWORD=tm_local_<third-32-96-url-safe-secret>
```

Expected:

- `git check-ignore` prints `.env.local`; `git status --short` does not list it.
- Passwords are synthetic and used only for this local workspace.
- The three URLs are the only host/port facts; no `POSTGRES_PORT`, `REDIS_PORT`, separate container URL, or Compose override is created.
- Do not paste generated values into an issue, PR, test fixture, or acceptance transcript.

## 3. Cold start with or without cached images

```bash
make dev
```

Expected:

- The output identifies a safe `tokenmarket-<12-hex>` project ID and never prints the source path.
- If an image is missing, `image-pull` events appear separately for `postgres`, `redis`, and `grafana`; only committed digest identities are fetched.
- The 60-second readiness timing starts after all image identities are locally available.
- Compose reconcile and all three fresh authenticated probes finish inside that one deadline; there is no second post-wait probe budget.
- Final per-dependency evidence shows:
  - PostgreSQL authenticated query ready;
  - Redis authenticated `PING` ready;
  - Grafana health database and administrator identity ready.
- Host endpoints are displayed without user-info/passwords and use only `127.0.0.1`.
- Aggregate exit is 0 only after all three are ready. Kafka/Redpanda, Prometheus, Loki, MinIO, frontend, gateway, and Python services are not started.
- JSONL output validates as a standard event v2 envelope with unique event IDs, UTC timestamps, stable producer/type, one lifecycle correlation ID and strict dependency payloads; plain text communicates the same safe state without requiring color, icons, animation or interaction.

If readiness fails, do not remove volumes. Follow the reported dependency/code, inspect only the safe diagnostic command described by the runbook, fix the cause, and run `make dev` again.

## 4. Confirm idempotent repeat start

Run this ten times against the healthy environment:

```bash
make dev
```

Expected for every run:

- Completion within 15 seconds.
- No registry access or image pull.
- Same project ID, services, network, and PostgreSQL/Redis volume identities.
- No duplicate container, network, named volume, or Grafana anonymous volume.
- PostgreSQL and Redis content is not changed merely by confirmation.

Automated integration tests capture resource counts before/after all ten runs; manual validation need not parse Docker table output.

## 5. Verify stable host and container connection contracts

The successful `make dev` probes already validate host addresses and authenticated operations. Review the safe output and [`contracts/local-environment-lifecycle.md`](./contracts/local-environment-lifecycle.md):

| Dependency | Host process address | Container-network address |
|------------|----------------------|---------------------------|
| PostgreSQL | URL from `DATABASE_URL` | same URL with `postgres:5432` and original user/database |
| Redis | URL from `REDIS_URL` | same URL with `redis:6379` and original DB number |
| Grafana | URL from `GRAFANA_URL` | `http://grafana:3000` |

Expected:

- Host publishers bind `127.0.0.1`, not `0.0.0.0`.
- Container DNS names are exactly `postgres`, `redis`, `grafana` on the project network.
- No developer-maintained second container URL exists.

The real integration suite creates a short-lived test-only container on the exact project network. It receives synthetic probe material over stdin, then uses the canonical container URLs to execute a PostgreSQL query, Redis AUTH/PING, and Grafana health/admin HTTP requests. DNS resolution alone does not pass. Probe secrets do not enter argv, environment, inspect output or retained evidence, and the probe is never part of `make dev` success.

## 6. Validate API Service PostgreSQL readiness

With dependencies running, start API Service in a separate terminal without copying configuration:

```bash
cd services/api-service
uv run --locked --env-file ../../.env.local uvicorn app.main:app --host 127.0.0.1 --port 8000
```

From another terminal:

```bash
curl -fsS http://127.0.0.1:8000/health/live
curl -fsS http://127.0.0.1:8000/health/ready
```

Expected:

- Liveness is 200 with `status=alive`.
- Readiness is 200 with the unchanged SF01 success shape and `status=ready`.
- No URL, username, SQL exception, or password appears in response/logs.
- `/metrics` increments `tokenmarket_postgres_readiness_probes_total`, observes `tokenmarket_postgres_readiness_probe_duration_seconds`, and leaves `tokenmarket_postgres_readiness_probe_failures_total` unchanged for a successful probe; no metric label contains configuration or exception data.

Stop only PostgreSQL through the test fault-injection helper owned by the automated suite (do not hand-edit or delete volumes in this guide). The service contract tests prove:

- liveness remains 200;
- readiness becomes 503 within the two-second probe bound;
- the body names only `postgres` with a stable safe code;
- the total and failure counters increment and the duration histogram observes the failed probe;
- after PostgreSQL recovery, readiness returns to 200 without restarting API Service.

## 7. Validate Billing Service PostgreSQL readiness

Repeat the previous procedure on a different port:

```bash
cd services/billing-service
uv run --locked --env-file ../../.env.local uvicorn app.main:app --host 127.0.0.1 --port 8001
```

```bash
curl -fsS http://127.0.0.1:8001/health/live
curl -fsS http://127.0.0.1:8001/health/ready
```

Expected behavior, metrics and recovery are identical to API Service. Gateway and Admin Service must retain their SF01 readiness behavior and must not gain a PostgreSQL probe in SF02.

Stop the local Uvicorn processes before continuing. They are not lifecycle-managed by `make dev-down`.

## 8. Non-destructive stop and repeated stop

```bash
make dev-down
make dev-down
```

Expected:

- First call removes only exact-project containers/orphans and temporary network after bounded graceful termination.
- PostgreSQL and Redis named volumes remain; no `--volumes`, image removal, prune, schema action, or seed action occurs.
- Grafana `/var/lib/grafana` is tmpfs, so state is recreated and no anonymous volume remains; dashboards/data sources are not SF02 assets.
- Second call returns 0 and reports `already stopped` without touching another workspace.
- `already stopped` means no exact-project container or network exists; a stopped container from a failed start is still removed.
- The command succeeds even if `.env.local` has been temporarily moved aside, because identity and down do not depend on secrets.

Restore `.env.local` if moved and run `make dev` again. Automated persistence evidence inserts a marker into PostgreSQL, cycles start/down ten times, and verifies 100% retention; it also clears Redis fixture content and proves correctness is unchanged.

## 9. Validate safe port-conflict failure

With the SF02 environment stopped, occupy the configured Grafana port in a disposable terminal:

```bash
python3 -m http.server 3000 --bind 127.0.0.1
```

In another terminal:

```bash
make dev
```

Expected:

- Non-zero `PORT_CONFLICT` names `grafana` and port `3000` before creating new project resources.
- The workflow sends no Grafana credential/request to the unrelated HTTP server and never stops it.
- PostgreSQL/Redis are not partially created for this clean-start case.

Stop the disposable HTTP server, then rerun `make dev`; it should converge normally.

## 10. Validate negative and recovery suites

Run repository tests rather than placing real unsafe values into this workspace:

```bash
make test
```

Expected SF02 coverage includes:

- missing/placeholder/malformed config, non-loopback URLs, duplicate/invalid ports, and non-local mode;
- Docker/Compose/daemon/platform/remote-context failures before state changes;
- image pull/digest/platform mismatch with readiness timing not started;
- PostgreSQL query/auth, Redis auth/PING, and Grafana health/admin failures;
- stale health, stopped containers, partial start, daemon loss, command interrupt, and direct retry;
- lock contention, secure lock-path symlink/owner/mode rejection, repeated start, start-versus-down conflict, abnormal lock-holder exit, and port bind race;
- Unicode/space/symlink paths, same-path stable identity, different clone/worktree isolation, short-hash collision failure, and move detection;
- committed Compose-byte/stdin transport, safe runtime project directory, dirty/symlink Compose asset rejection, and absence of raw/canonical workspace paths from every custom and Compose canonical label;
- local-secret grammar/config-injection rejection and redaction across plaintext, JSONL, child environment, Compose/inspect errors and tests;
- environment-source secret UID/GID/mode checks, non-root PID 1 checks, Grafana tmpfs and zero anonymous volumes;
- dirty tracked and untracked worktree snapshots proving dev/dev-down change no workspace file;
- `NO_COLOR`, plain-text, non-interactive and screen-reader terminal output regressions;
- disposable fixture cleanup that never addresses developer project resources.

The test target may create only isolated, test-labeled Compose projects with dynamic loopback ports and synthetic data. It must not stop or delete the developer environment from Sections 3–8.

## 11. Platform acceptance matrix

Run Sections 1–10 on representative hosts through the same committed deterministic performance harness and retain separate timing summaries. For SC-001, each host executes one predeclared batch of 20 valid cold trials: images are present and verified before timing, every trial starts with no project container/network and fresh isolated test-owned volumes, and at least 19 of 20 must make all three dependencies ready within 60 seconds. Count every valid trial; a prerequisite/toolchain failure invalidates and reruns the complete batch rather than dropping an individual slow result.

| Host | Container variant | Required evidence |
|------|-------------------|-------------------|
| macOS arm64 | `linux/arm64` native | Path/NFC identity, Desktop loopback forwarding, health, graceful stop, 95% ≤60s and repeat ≤15s |
| Linux x86_64 | `linux/amd64` native | Unix socket permissions, loopback publishing, health, graceful stop, 95% ≤60s and repeat ≤15s |

The public Make targets, config fields, project ID, service names, health rules, event schema, persistence semantics, and pass/fail behavior must be identical. Do not force `linux/amd64` on macOS arm64.

For SC-008, the repository workflow owner recruits 10 representative developers with no prior SF02 use using the committed participant criteria and evidence template. From a prerequisite-ready checkout, time each person using only root help and the local-environment documentation; at least 9 of 10 must independently prepare configuration, start, confirm all three dependency states, and locate one injected-failure recovery instruction within 10 minutes. Record only aggregate timings/results and safe observations.

## 12. Review evidence

Attach only redacted artifacts:

- `make help` and toolchain capability result.
- Per-platform 20-trial cold-start summaries showing at least 19/20 within 60 seconds, with image timing excluded, plus ten healthy repeat timings.
- Per-dependency final records validated against the workflow event v2 standard envelope, plus v1 Make/event immutability and consumer-migration evidence.
- Ten start/down/restart cycles with PostgreSQL marker retention and stable resource counts.
- API/Billing 200/503/recovery contract results.
- Port conflict, invalid config, auth failure, timeout, lock conflict, moved-workspace, and remote-context results.
- Linux x86_64 and macOS arm64 performance summaries.
- Ten-person new-developer acceptance aggregate showing at least 9/10 within 10 minutes.
- Image tag/index/child digests, license review, and scans for both architectures.
- `git status --short` proving no runtime config, secret, generated override, or unrelated workspace change was tracked.

Do not attach `.env.local`, raw Compose config/inspect output, child environment/secret content, URLs with user-info, or dependency exception bodies.

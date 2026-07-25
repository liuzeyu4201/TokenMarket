# TokenMarket repository workflow baseline.
# This is the only public workflow entry point.

# Resolve repository root from the current working directory. This supports
# paths containing spaces or non-ASCII characters, which word-splitting on
# MAKEFILE_LIST cannot safely handle.
REPO_ROOT := $(CURDIR)
export REPO_ROOT

# Mode selection is deliberately strict. Only an explicit command-line origin
# may select test or prod; shell/environment/file origins are ignored.
MODE ?= $(mode)
MODE_ORIGIN := $(origin mode)

# Local start/stop scope: all (middleware + apps) or apps (host processes only).
# Middleware-only operations keep their existing make dev/dev-down contract.
SCOPE ?= $(scope)
ifeq ($(SCOPE),)
SCOPE := all
endif
export TOKENMARKET_START_SCOPE := $(SCOPE)

# Optional host port overrides: pass on the Make command line, e.g.
#   make start scope=apps API_HOST_PORT=18000
# Command-line Make variables are exported to the recipe environment by default.
# RESTART_PROCESS=1 forces main-process restart even when liveness already passes.

# Default target shows help without side effects.
.PHONY: help
help:
	@echo "TokenMarket repository workflow"
	@echo ""
	@echo "Daily local development:"
	@echo "  make start          Start middleware + gateway/api/billing/admin/frontend"
	@echo "  make stop           Stop the complete local environment; retain PG/Redis data"
	@echo ""
	@echo "One-time preparation:"
	@echo "  make toolchain-check Verify declared tool versions"
	@echo "  make bootstrap       Prepare locked project dependencies"
	@echo "  make migrate         Apply reviewed migrations; local reads ignored .env.local"
	@echo ""
	@echo "Advanced local operations:"
	@echo "  make dev             Start only PostgreSQL/Redis/Grafana (SF02 activation pending)"
	@echo "  make dev-down        Stop only middleware; retain PG/Redis data"
	@echo "  make start scope=apps Start only host application processes"
	@echo "  make stop scope=apps  Stop only host application processes"
	@echo "  RESTART_PROCESS=1     Force restart app processes instead of healthy reuse"
	@echo "  *_HOST_PORT=…         Override app ports only; middleware ports come from .env.local"
	@echo ""
	@echo "Test and delivery:"
	@echo "  make deploy         Deploy middleware+apps (requires mode=test|prod)"
	@echo "  make deploy-down    Stop deploy stack; retain named volumes (requires mode=test|prod)"
	@echo "  make fmt            Apply repository formatters (modifies source)"
	@echo "  make lint           Run static analysis, type checks and boundary checks"
	@echo "  make test           Run all component tests"
	@echo "  make build          Build five service images and three asset bundles"
	@echo "  make ci             Run the complete CI gate"
	@echo ""
	@echo "Support targets:"
	@echo "  make type-check     Run the complete type-check set independently"
	@echo "  make security-check Run secret and dependency scans (fail-closed)"
	@echo ""
	@echo "Prerequisites: Go, Python/uv, Node/npm, Docker (see .tool-versions)"
	@echo "Side effects: start/dev may create exact-workspace containers and volumes;"
	@echo "  start reloads .env.local; changed app config restarts affected processes;"
	@echo "  unchanged healthy resources/processes are reused; stop keeps PG/Redis volumes;"
	@echo "  application processes run on the host, never in compose.local.yml."
	@echo "Recovery: fix the reported diagnostic and rerun the same start command;"
	@echo "  app-only restart: make start scope=apps RESTART_PROCESS=1."
	@echo "Layers: local = host apps + middleware; test/prod = make build then make deploy mode=…"

# Public targets delegate to the maintained workflow tool.
.PHONY: start stop dev dev-down deploy deploy-down fmt lint test build migrate
.PHONY: bootstrap type-check toolchain-check fmt-check migrate-check migrate-integration-check security-check runtime-smoke image-scan

dev dev-down start stop deploy deploy-down fmt lint test build migrate bootstrap type-check toolchain-check fmt-check migrate-check migrate-integration-check security-check runtime-smoke image-scan:
	@uv run --project "$(REPO_ROOT)/tools/workflow" python -m workflow.cli \
		"$@" \
		$(if $(MODE),--mode $(MODE)) \
		--mode-origin "$(MODE_ORIGIN)" \
		--scope "$(SCOPE)" \
		--repo-root "$(REPO_ROOT)"

# CI gate: fixed ordering, fail-fast, single public entry point. Every step uses
# the same root Makefile adapters so local and hosted runs are identical.
.PHONY: ci
ci: toolchain-check bootstrap fmt-check type-check lint test migrate-check migrate-integration-check security-check build runtime-smoke image-scan
	@echo "CI gate passed"

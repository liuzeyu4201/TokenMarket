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

# Default target shows help without side effects.
# Activation-ready copy for SF02 lifecycle targets is prepared here (T047) but
# remains descriptive until the final atomic public switch (T074). Until then
# both targets still fail closed with SF02_NOT_READY at runtime.
# Deploy targets (ADR 003) are listed and fail closed until deploy_env lands.
.PHONY: help
help:
	@echo "TokenMarket repository workflow"
	@echo ""
	@echo "Public targets:"
	@echo "  make dev            Start local PostgreSQL/Redis/Grafana (SF02; adapter ready, public activation pending evidence)"
	@echo "  make dev-down       Stop local runtime instances; retain named volumes (SF02; public activation pending)"
	@echo "  make deploy         Deploy middleware+apps stack (ADR 003; requires mode=test|prod)"
	@echo "  make deploy-down    Stop deploy stack; retain named volumes (requires mode=test|prod)"
	@echo "  make fmt            Apply repository formatters (modifies source)"
	@echo "  make lint           Run static analysis, type checks and boundary checks"
	@echo "  make test           Run all component tests"
	@echo "  make build          Build five service images and three asset bundles"
	@echo "  make migrate        Apply reviewed migrations to selected environment"
	@echo ""
	@echo "Support targets:"
	@echo "  make bootstrap      Prepare locked project dependencies"
	@echo "  make type-check     Run the complete type-check set independently"
	@echo "  make toolchain-check Verify declared tool versions"
	@echo "  make security-check Run secret and dependency scans (fail-closed)"
	@echo ""
	@echo "Prerequisites: Go, Python/uv, Node/npm, Docker (see .tool-versions)"
	@echo "Side effects: fmt modifies declared source; build creates local images;"
	@echo "  dev creates local project containers/networks/volumes; dev-down stops runtime"
	@echo "  instances and keeps PostgreSQL/Redis named volumes (no prune/volume delete);"
	@echo "  deploy/deploy-down target shared test|prod stacks (gated until adapter lands)"
	@echo "Recovery: fix the reported diagnostic (mode/config/port/auth/runtime) and"
	@echo "  rerun the same command; for moved workspaces use the original path identity"
	@echo "Layers: local apps are host processes + make dev middleware; test/prod use"
	@echo "  make build then make deploy mode=test|prod (see docs/decisions/003-layered-compose-deploy.md)"

# Public targets delegate to the maintained workflow tool.
.PHONY: dev dev-down deploy deploy-down fmt lint test build migrate
.PHONY: bootstrap type-check toolchain-check fmt-check migrate-check migrate-integration-check security-check runtime-smoke image-scan

dev dev-down deploy deploy-down fmt lint test build migrate bootstrap type-check toolchain-check fmt-check migrate-check migrate-integration-check security-check runtime-smoke image-scan:
	@uv run --project "$(REPO_ROOT)/tools/workflow" python -m workflow.cli \
		"$(subst migrate-check,migrate-check,$@)" \
		$(if $(MODE),--mode $(MODE)) \
		--mode-origin "$(MODE_ORIGIN)" \
		--repo-root "$(REPO_ROOT)"

# CI gate: fixed ordering, fail-fast, single public entry point. Every step uses
# the same root Makefile adapters so local and hosted runs are identical.
.PHONY: ci
ci: toolchain-check bootstrap fmt-check type-check lint test migrate-check migrate-integration-check security-check build runtime-smoke image-scan
	@echo "CI gate passed"

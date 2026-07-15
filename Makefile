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
.PHONY: help
help:
	@echo "TokenMarket repository workflow"
	@echo ""
	@echo "Public targets:"
	@echo "  make dev            Start local dependencies after SF02"
	@echo "  make dev-down       Stop local dependencies after SF02"
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
	@echo "Side effects: fmt modifies declared source files; build creates local images"
	@echo "Recovery: fix the reported component error and rerun the same command"

# Public targets delegate to the maintained workflow tool.
.PHONY: dev dev-down fmt lint test build migrate
.PHONY: bootstrap type-check toolchain-check fmt-check migrate-check migrate-integration-check security-check runtime-smoke image-scan

dev dev-down fmt lint test build migrate bootstrap type-check toolchain-check fmt-check migrate-check migrate-integration-check security-check runtime-smoke image-scan:
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

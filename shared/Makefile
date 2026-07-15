# Shared contracts asset workflow adapter.

.PHONY: bootstrap fmt fmt-check type-check lint test build

bootstrap:
	uv sync --locked --project ../tools/workflow

fmt:
	uv run --project ../tools/workflow --locked black --config ../tools/workflow/pyproject.toml tools tests
	uv run --project ../tools/workflow --locked isort --settings-path ../tools/workflow/pyproject.toml tools tests

fmt-check:
	uv run --project ../tools/workflow --locked black --config ../tools/workflow/pyproject.toml --check tools tests
	uv run --project ../tools/workflow --locked isort --settings-path ../tools/workflow/pyproject.toml --check-only tools tests

type-check:
	uv run --project ../tools/workflow --locked mypy tools tests

lint: fmt-check type-check
	uv run --project ../tools/workflow --locked flake8 --max-line-length 100 tools tests
	uv run --project ../tools/workflow --locked python tools/validate_contracts.py

test:
	uv run --project ../tools/workflow --locked pytest tests

build:
	uv run --project ../tools/workflow --locked python tools/validate_contracts.py

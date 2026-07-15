# Operations asset workflow adapter.

.PHONY: bootstrap fmt fmt-check type-check lint test build

bootstrap:
	uv sync --locked --project ../tools/workflow

fmt:
	uv run --project ../tools/workflow --locked black tools tests
	uv run --project ../tools/workflow --locked isort tools tests

fmt-check:
	uv run --project ../tools/workflow --locked black --check tools tests
	uv run --project ../tools/workflow --locked isort --check-only tools tests

type-check:
	uv run --project ../tools/workflow --locked mypy tools tests

lint: fmt-check type-check
	uv run --project ../tools/workflow --locked flake8 tools tests
	uv run --project ../tools/workflow --locked python tools/validate_assets.py

test:
	uv run --project ../tools/workflow --locked pytest tests

build:
	uv run --project ../tools/workflow --locked python tools/validate_assets.py

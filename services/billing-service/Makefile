# Billing Service internal workflow adapter.

.PHONY: bootstrap fmt fmt-check type-check lint test build migrate

IMAGE_TAG ?= tokenmarket/billing-service:0.1.0

bootstrap:
	uv sync --locked

fmt:
	uv run --locked --group dev black app tests
	uv run --locked --group dev isort app tests

fmt-check:
	uv run --locked --group dev black --check app tests
	uv run --locked --group dev isort --check-only app tests

type-check:
	uv run --locked --group dev mypy app

lint: fmt-check type-check
	uv run --locked --group dev flake8 --max-line-length 88 app tests

test:
	PYTHONPATH=. uv run --locked --group dev pytest --cov=app --cov-report=term-missing tests

build:
	docker build -t $(IMAGE_TAG) .

migrate:
	uv run --locked --group dev alembic upgrade head

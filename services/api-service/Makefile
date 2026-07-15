# API Service internal workflow adapter.

.PHONY: bootstrap fmt fmt-check type-check lint test build migrate

IMAGE_TAG ?= tokenmarket/api-service:0.1.0

bootstrap:
	uv sync --locked

fmt:
	uv run --locked --extra dev black app tests
	uv run --locked --extra dev isort app tests

fmt-check:
	uv run --locked --extra dev black --check app tests
	uv run --locked --extra dev isort --check-only app tests

type-check:
	uv run --locked --extra dev mypy app

lint: fmt-check type-check
	uv run --locked --extra dev flake8 --max-line-length 88 app tests

test:
	PYTHONPATH=. uv run --locked --extra dev pytest --cov=app --cov-report=term-missing tests

build:
	docker build -t $(IMAGE_TAG) .

migrate:
	uv run --locked alembic upgrade head

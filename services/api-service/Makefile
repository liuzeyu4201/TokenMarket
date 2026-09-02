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
	PYTHONPATH=. uv run --locked --extra dev pytest \
		--cov=app \
		--cov-report=term-missing \
		--cov-fail-under=0 \
		tests
	# Domain registration packages must stay ≥80% (Constitution V / T072)
	PYTHONPATH=. uv run --locked --extra dev pytest \
		--cov=app.domain.users \
		--cov=app.api.v1.auth \
		--cov=app.rate_limit \
		--cov-report=term-missing \
		--cov-fail-under=80 \
		tests/unit tests/integration -q
	# Authentication domain/route packages must stay ≥80% (004 T017/T029)
	PYTHONPATH=. uv run --locked --extra dev pytest \
		--cov=app.domain.authentication \
		--cov=app.security \
		--cov=app.api.v1.auth \
		--cov=app.dispatch \
		--cov-report=term-missing \
		--cov-fail-under=80 \
		tests/unit tests/integration -q
	# Seller/proxy/usage domain packages must stay ≥80% (SF08–SF17)
	PYTHONPATH=. uv run --locked --extra dev pytest \
		--cov=app.domain.sellerkeys \
		--cov=app.domain.proxykeys \
		--cov=app.domain.usage \
		--cov=app.api.v1.seller_keys \
		--cov=app.api.v1.proxy_keys \
		--cov=app.api.v1.internal \
		--cov-report=term-missing \
		--cov-fail-under=80 \
		tests/unit tests/integration -q
	# Buyer Project domain must stay ≥80% (SF10)
	PYTHONPATH=. uv run --locked --extra dev pytest \
		--cov=app.domain.projects \
		--cov=app.api.v1.projects \
		--cov-report=term-missing \
		--cov-fail-under=80 \
		tests/unit tests/integration -q
	# Provider Binding domain must stay ≥80% (SF11)
	PYTHONPATH=. uv run --locked --extra dev pytest \
		--cov=app.domain.bindings \
		--cov=app.api.v1.bindings \
		--cov-report=term-missing \
		--cov-fail-under=80 \
		tests/unit tests/integration -q
	# Provider Connection domain must stay ≥80% (SF14)
	PYTHONPATH=. uv run --locked --extra dev pytest \
		--cov=app.domain.connections \
		--cov=app.api.v1.connections \
		--cov-report=term-missing \
		--cov-fail-under=80 \
		tests/unit tests/integration -q
	# V0.2 Goal: 鉴权 domain branch coverage ≥90% (does not replace the 80% line gates)
	PYTHONPATH=. uv run --locked --extra dev pytest \
		--cov=app.domain.authentication \
		--cov=app.security \
		--cov-branch \
		--cov-report=term-missing \
		--cov-fail-under=90 \
		tests/unit -q
	# V0.2 Goal: 权限 domain branch coverage ≥90%
	PYTHONPATH=. uv run --locked --extra dev pytest \
		--cov=app.domain.authorization \
		--cov-branch \
		--cov-report=term-missing \
		--cov-fail-under=90 \
		tests/unit -q

build:
	docker build -t $(IMAGE_TAG) .

migrate:
	uv run --locked alembic upgrade head

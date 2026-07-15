# Frontend internal workflow adapter.

.PHONY: bootstrap fmt fmt-check type-check lint test build

IMAGE_TAG ?= tokenmarket/frontend:0.1.0

bootstrap:
	npm ci

fmt:
	npx prettier --write .

fmt-check:
	npx prettier --check .

type-check:
	npx tsc --noEmit

lint: type-check
	npx eslint .

test:
	npx vitest run

build:
	npx tsc -b && npx vite build
	docker build -t $(IMAGE_TAG) .

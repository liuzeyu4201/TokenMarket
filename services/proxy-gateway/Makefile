# Proxy Gateway internal workflow adapter.

.PHONY: bootstrap fmt fmt-check type-check lint test build

IMAGE_TAG ?= tokenmarket/proxy-gateway:0.1.0

bootstrap:
	go mod download

fmt:
	gofmt -w cmd internal

fmt-check:
	@test -z "$$(gofmt -l cmd internal)" || (gofmt -l cmd internal; exit 1)

type-check:
	go vet ./...

lint: fmt-check type-check
	@echo "lint: proxy-gateway passed"

test:
	go test -race -coverprofile=coverage.out ./...

build:
	docker build -t $(IMAGE_TAG) .

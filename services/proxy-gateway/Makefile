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
	# V0.2 Goal: 鉴权/路由 domain statement coverage ≥90% (Go has no --cov-branch)
	@for pkg in proxyauth qualify score; do \
		go test -coverprofile=/tmp/tm-$$pkg.out ./internal/domain/$$pkg/; \
		pct=$$(go tool cover -func=/tmp/tm-$$pkg.out | awk '/^total:/{print $$NF}'); \
		python3 -c "import sys; p=float('$${pct}'.rstrip('%')); sys.exit(0 if p>=90.0 else 1)" \
			|| { echo "$$pkg coverage $$pct < 90%"; exit 1; }; \
		echo "$$pkg coverage $$pct"; \
	done

build:
	docker build -t $(IMAGE_TAG) .

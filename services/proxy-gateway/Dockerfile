# Build stage
FROM golang:1.25.14-alpine AS builder

WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download

COPY cmd ./cmd
COPY internal ./internal

RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o gateway ./cmd/gateway

# Runtime stage
FROM gcr.io/distroless/static-debian12@sha256:cdf4daaf154e3e27cfffc799c16f343a384228f38646928a1513d925f473cb46

WORKDIR /app
COPY --from=builder /build/gateway /app/gateway

USER nonroot:nonroot
EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD ["/app/gateway"] || exit 1

CMD ["/app/gateway"]

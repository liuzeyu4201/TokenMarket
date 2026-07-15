# Build stage
FROM node:24.18.0-slim AS builder

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Runtime stage
FROM nginx:1.27.4-alpine@sha256:4ff102c5d78d254a6f0da062b3cf39eaf07f01eec0927fd21e219d0af8bc0591

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN addgroup -S appgroup && adduser -S appuser -G appgroup && \
    mkdir -p /var/cache/nginx /var/run /var/log/nginx /tmp && \
    sed -i '/pid.*nginx.pid;/d' /etc/nginx/nginx.conf && \
    chown -R appuser:appgroup /var/cache/nginx /var/run /var/log/nginx /tmp /usr/share/nginx/html /etc/nginx /etc/nginx/conf.d
USER appuser

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://localhost:3000/health/live || exit 1

CMD ["nginx", "-g", "pid /tmp/nginx.pid; daemon off;"]

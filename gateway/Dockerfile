# Build stage
FROM golang:1.25.9-alpine AS builder

# CN mirror support — pass via --build-arg or docker compose .env
ARG GOPROXY=https://proxy.golang.org,direct
ARG ALPINE_MIRROR
ENV GOPROXY=${GOPROXY}

WORKDIR /app

# Install build dependencies
# hadolint ignore=SC2086
RUN if [ -n "$ALPINE_MIRROR" ]; then \
      sed -i "s|dl-cdn.alpinelinux.org|${ALPINE_MIRROR}|g" /etc/apk/repositories; \
    fi && \
    apk add --no-cache git make

# Copy go mod files
COPY go.mod go.sum* ./
RUN go mod download

# Copy source
COPY . .

# Build binary
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-w -s" -o /gateway ./cmd/gateway

# Runtime stage
FROM alpine:3.23

ARG ALPINE_MIRROR

WORKDIR /app

# Install CA certificates for HTTPS
# hadolint ignore=SC2086
RUN if [ -n "$ALPINE_MIRROR" ]; then \
      sed -i "s|dl-cdn.alpinelinux.org|${ALPINE_MIRROR}|g" /etc/apk/repositories; \
    fi && \
    apk add --no-cache ca-certificates tzdata

# Copy binary from builder
COPY --from=builder /gateway /app/gateway

# Create non-root user
RUN adduser -D -g '' appuser
USER appuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

# Run
ENTRYPOINT ["/app/gateway"]

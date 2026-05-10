FROM rust:1.94-alpine AS builder

ARG ALPINE_MIRROR

WORKDIR /app

RUN if [ -n "$ALPINE_MIRROR" ]; then \
      sed -i "s|dl-cdn.alpinelinux.org|${ALPINE_MIRROR}|g" /etc/apk/repositories; \
    fi && \
    apk add --no-cache musl-dev protobuf-dev

COPY rust ./rust
COPY agents/requirement_manager/grpc/proto ./agents/requirement_manager/grpc/proto

RUN cargo build --manifest-path rust/Cargo.toml --release -p wisdoverse-cell-rust-gateway

FROM alpine:3.23

ARG ALPINE_MIRROR

WORKDIR /app

RUN if [ -n "$ALPINE_MIRROR" ]; then \
      sed -i "s|dl-cdn.alpinelinux.org|${ALPINE_MIRROR}|g" /etc/apk/repositories; \
    fi && \
    apk add --no-cache ca-certificates tzdata wget

COPY --from=builder /app/rust/target/release/wisdoverse-cell-rust-gateway /app/gateway

RUN adduser -D -g '' appuser
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

ENTRYPOINT ["/app/gateway"]

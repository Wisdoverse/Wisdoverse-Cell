.PHONY: all build run test clean proto deps

# Variables
BINARY_NAME=gateway
GO=go
PROTOC=protoc

# Build
all: proto build

build:
	$(GO) build -o bin/$(BINARY_NAME) ./cmd/gateway

run: build
	./bin/$(BINARY_NAME)

# Proto generation
proto:
	$(PROTOC) --go_out=. --go_opt=paths=source_relative \
		--go-grpc_out=. --go-grpc_opt=paths=source_relative \
		api/proto/*.proto

# Dependencies
deps:
	$(GO) mod download
	$(GO) mod tidy

# Test
test:
	$(GO) test -v ./...

test-coverage:
	$(GO) test -coverprofile=coverage.out -covermode=atomic \
		$$(go list ./... | grep -v /api/proto | grep -v /cmd/)
	$(GO) tool cover -html=coverage.out -o coverage.html

# Clean
clean:
	rm -rf bin/
	rm -f coverage.out coverage.html

# Development
dev:
	$(GO) run ./cmd/gateway

# Lint
lint:
	golangci-lint run ./...

# Docker
docker-build:
	docker build -t project-cell-gateway:latest .

# Help
help:
	@echo "Available targets:"
	@echo "  all          - Generate proto and build"
	@echo "  build        - Build the binary"
	@echo "  run          - Build and run"
	@echo "  proto        - Generate protobuf code"
	@echo "  deps         - Download dependencies"
	@echo "  test         - Run tests"
	@echo "  clean        - Clean build artifacts"
	@echo "  dev          - Run in development mode"
	@echo "  lint         - Run linter"

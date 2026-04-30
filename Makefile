# Wisdoverse Cell - Makefile

.PHONY: all proto proto-python proto-go setup test test-public test-unit test-unit-full test-integration test-e2e test-python-full install dev

PYTEST ?= python -m pytest

PYTEST_PUBLIC_PATHS = \
	tests/unit/test_config_secrets.py \
	tests/unit/test_middleware.py \
	shared/integrations/feishu/tests \
	shared/integrations/wecom/tests \
	shared/tests/test_event_payloads.py \
	agents/requirement_manager/tests/test_grpc_servicer.py

PYTEST_UNIT_PATHS = \
	tests/unit \
	shared/tests/unit \
	shared/infra/tests/test_vector_store.py \
	shared/tests/test_event_payloads.py \
	shared/integrations/feishu/tests \
	shared/integrations/wecom/tests \
	agents/requirement_manager/tests/test_grpc_servicer.py

PYTEST_UNIT_FULL_ARGS = \
	tests/unit \
	shared/tests/unit \
	agents/*/tests/unit \
	skills/tests \
	shared/integrations/feishu/tests \
	shared/integrations/wecom/tests \
	agents/requirement_manager/tests/test_grpc_servicer.py \
	--ignore=skills/tests/test_skills_integration.py

PYTEST_INTEGRATION_PATHS = \
	tests/integration \
	shared/tests/integration \
	agents/*/tests/integration \
	shared/messaging/outbound/tests/integration

PYTEST_E2E_PATHS = \
	tests/e2e \
	agents/requirement_manager/tests/e2e

# === Proto Generation ===

proto: proto-python proto-go

proto-python:
	@echo "Generating Python gRPC code..."
	python -m grpc_tools.protoc \
		-I shared/grpc/proto \
		--python_out=shared/grpc/generated \
		--grpc_python_out=shared/grpc/generated \
		shared/grpc/proto/requirement.proto
	@echo "Python gRPC code generated."

proto-go:
	@echo "Generating Go gRPC code..."
	cd gateway && $(MAKE) proto
	@echo "Go gRPC code generated."

# === Development ===

install:
	pip install -r requirements.txt

setup:
	python -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

dev:
	uvicorn agents.requirement_manager.app.main:app --reload --port 8000

grpc-server:
	python -m shared.grpc.server

# === Testing ===

test: test-public

test-public:
	$(PYTEST) -q $(PYTEST_PUBLIC_PATHS)

test-unit:
	$(PYTEST) -q $(PYTEST_UNIT_PATHS)

test-unit-full:
	$(PYTEST) -q $(PYTEST_UNIT_FULL_ARGS)

test-integration:
	$(PYTEST) -q $(PYTEST_INTEGRATION_PATHS)

test-e2e:
	$(PYTEST) -q $(PYTEST_E2E_PATHS)

test-python-full:
	$(PYTEST) -q agents shared tests skills

# === Gateway ===

gateway-build:
	cd gateway && $(MAKE) build

gateway-run:
	cd gateway && $(MAKE) run

gateway-dev:
	cd gateway && $(MAKE) dev

# === Frontend ===

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-lint:
	cd frontend && npm run lint

frontend-test:
	cd frontend && npm test

# === Docker (Cloud-Native) ===


# Compose file paths
COMPOSE_BASE   = -f docker/compose/docker-compose.base.yml
COMPOSE_APP    = -f docker/compose/docker-compose.app.yml
COMPOSE_PROXY  = -f docker/compose/docker-compose.proxy.yml
COMPOSE_OBS    = -f docker/compose/docker-compose.observability.yml
COMPOSE_DEV    = -f docker/compose/docker-compose.override.yml
COMPOSE_PROD   = -f docker/compose/docker-compose.prod.yml
COMPOSE_LOAD   = -f docker/compose/docker-compose.loadtest.yml

# Development (single replica + debug ports)
up-dev:
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) $(COMPOSE_DEV) up -d

down-dev:
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) $(COMPOSE_DEV) down

# Production (multi-replica + observability + no debug)
up-prod:
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) $(COMPOSE_OBS) $(COMPOSE_PROD) up -d

down-prod:
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) $(COMPOSE_OBS) $(COMPOSE_PROD) down

# Infrastructure only (for local code development)
up-infra:
	docker compose $(COMPOSE_BASE) $(COMPOSE_DEV) up -d

down-infra:
	docker compose $(COMPOSE_BASE) $(COMPOSE_DEV) down

# Legacy mode (original single docker-compose.yml)
up:
	docker compose up -d

down:
	docker compose down

# Logs & Status
logs:
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) logs -f

logs-app:
	docker compose $(COMPOSE_APP) logs -f

ps:
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) ps

# Build
build:
	docker compose $(COMPOSE_APP) build

build-no-cache:
	docker compose $(COMPOSE_APP) build --no-cache

# Scaling
scale-gateway: ## Scale Gateway replicas (usage: make scale-gateway N=5)
	docker compose $(COMPOSE_APP) up -d --scale gateway=$(N) --no-recreate

scale-ai-core: ## Scale AI Core replicas (usage: make scale-ai-core N=5)
	docker compose $(COMPOSE_APP) up -d --scale ai-core=$(N) --no-recreate

scale-web: ## Scale Web frontend replicas (usage: make scale-web N=3)
	docker compose $(COMPOSE_APP) up -d --scale web=$(N) --no-recreate


# Monitoring (optional — needs base for infra exporters)
monitoring-up:
	docker compose $(COMPOSE_BASE) $(COMPOSE_OBS) up -d

monitoring-down:
	docker compose $(COMPOSE_BASE) $(COMPOSE_OBS) down

logs-obs:
	docker compose $(COMPOSE_OBS) logs -f

# Load Testing (k6)
load-smoke: ## Run k6 smoke test (10 VUs, 1 min)
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) $(COMPOSE_LOAD) run --rm -e K6_SCRIPT=k6_smoke.js k6

load-test: ## Run k6 load test (100 VUs, 8 min)
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) $(COMPOSE_LOAD) run --rm -e K6_SCRIPT=k6_load.js k6

load-stress: ## Run k6 stress test (up to 500 VUs, 13 min)
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) $(COMPOSE_LOAD) run --rm -e K6_SCRIPT=k6_stress.js k6

load-spike: ## Run k6 spike test (10→500→10 VUs)
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) $(COMPOSE_LOAD) run --rm -e K6_SCRIPT=k6_spike.js k6

# Testing
docker-test:
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit

# Restart
restart:
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) restart

# Cleanup
clean:
	docker compose $(COMPOSE_BASE) $(COMPOSE_APP) $(COMPOSE_PROXY) $(COMPOSE_OBS) down -v --remove-orphans 2>/dev/null || true
	docker compose down -v --remove-orphans 2>/dev/null || true
	docker system prune -f

# === Help ===

help:
	@echo "=== Wisdoverse Cell Makefile ==="
	@echo ""
	@echo "Development:"
	@echo "  make setup           - Create .venv and install Python dependencies"
	@echo "  make install         - Install Python dependencies"
	@echo "  make dev             - Run Python API server (hot-reload)"
	@echo "  make grpc-server     - Run Python gRPC server"
	@echo "  make test            - Run all tests"
	@echo ""
	@echo "Proto Generation:"
	@echo "  make proto           - Generate all protobuf code"
	@echo ""
	@echo "Gateway:"
	@echo "  make gateway-build   - Build Go gateway"
	@echo "  make gateway-dev     - Run Go gateway (dev mode)"
	@echo ""
	@echo "Docker (Cloud-Native):"
	@echo "  make up-dev          - Start dev environment (1 replica + debug ports)"
	@echo "  make up-prod         - Start prod environment (3 replicas)"
	@echo "  make up-infra        - Start infrastructure only"
	@echo "  make down-dev        - Stop dev environment"
	@echo "  make down-prod       - Stop prod environment"
	@echo "  make logs            - Follow all logs"
	@echo "  make ps              - Show running containers"
	@echo "  make build           - Build Docker images"
	@echo "  make scale-gateway N=5  - Scale Gateway replicas"
	@echo "  make scale-ai-core N=5  - Scale AI Core replicas"
	@echo ""
	@echo "Docker (Legacy):"
	@echo "  make up              - Start with root docker-compose.yml"
	@echo "  make down            - Stop root docker-compose.yml"
	@echo ""
	@echo "Monitoring:"
	@echo "  make monitoring-up   - Start observability stack (with infra)"
	@echo "  make monitoring-down - Stop observability stack"
	@echo "  make logs-obs        - Follow observability logs"
	@echo ""
	@echo "Load Testing (k6):"
	@echo "  make load-smoke      - Smoke test (10 VUs, 1 min)"
	@echo "  make load-test       - Load test (100 VUs, 8 min)"
	@echo "  make load-stress     - Stress test (up to 500 VUs, 13 min)"
	@echo "  make load-spike      - Spike test (10→500→10 VUs)"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean           - Remove all containers, volumes, prune"

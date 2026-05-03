#!/bin/bash
# Start or clean up the test environment.

set -e

COMPOSE_FILE="docker/docker-compose.test.yml"

case "$1" in
  up)
    echo "Starting test environment..."
    docker compose -f "$COMPOSE_FILE" up -d --wait
    echo "Test environment ready."
    ;;
  down)
    echo "Stopping test environment..."
    docker compose -f "$COMPOSE_FILE" down -v
    echo "Test environment stopped."
    ;;
  run)
    shift
    echo "Starting test environment..."
    docker compose -f "$COMPOSE_FILE" up -d --wait
    echo "Running tests..."
    .venv/bin/python -m pytest "$@"
    EXIT_CODE=$?
    echo "Stopping test environment..."
    docker compose -f "$COMPOSE_FILE" down -v
    exit $EXIT_CODE
    ;;
  *)
    echo "Usage: $0 {up|down|run [pytest args]}"
    echo ""
    echo "Examples:"
    echo "  $0 up                    # Start test containers"
    echo "  $0 down                  # Stop and cleanup"
    echo "  $0 run tests/e2e -v     # Run E2E tests"
    exit 1
    ;;
esac

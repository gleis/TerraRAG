#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
COMPOSE_FILE="$PROJECT_DIR/deploy/compose.yaml"
ENV_FILE="$PROJECT_DIR/deploy/.env"
RUNTIME=${TERRARAG_RUNTIME:-}

if [ -f "$ENV_FILE" ]; then
  : "${LLM_MODEL:=$(sed -n 's/^LLM_MODEL=//p' "$ENV_FILE" | tail -n 1)}"
  : "${EMBEDDING_MODEL:=$(sed -n 's/^EMBEDDING_MODEL=//p' "$ENV_FILE" | tail -n 1)}"
fi

LLM_MODEL=${LLM_MODEL:-gemma4:latest}
EMBEDDING_MODEL=${EMBEDDING_MODEL:-qwen3-embedding:0.6b}
export LLM_MODEL EMBEDDING_MODEL

if [ "$RUNTIME" = "docker" ] && ! docker info >/dev/null 2>&1; then
  echo "Docker is not running or is not accessible." >&2
  exit 1
fi
if [ "$RUNTIME" = "podman" ] && ! podman info >/dev/null 2>&1; then
  echo "Podman is not running or is not accessible." >&2
  exit 1
fi

compose() {
  if [ "$RUNTIME" = "docker" ]; then
    if [ -f "$ENV_FILE" ]; then
      docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
    else
      docker compose -f "$COMPOSE_FILE" "$@"
    fi
  elif podman compose version >/dev/null 2>&1; then
    if [ -f "$ENV_FILE" ]; then
      podman compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
    else
      podman compose -f "$COMPOSE_FILE" "$@"
    fi
  elif command -v podman-compose >/dev/null 2>&1; then
    if [ -f "$ENV_FILE" ]; then
      podman-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
    else
      podman-compose -f "$COMPOSE_FILE" "$@"
    fi
  else
    echo "Podman Compose is not available." >&2
    exit 1
  fi
}

wait_for_ollama() {
  attempts=60
  while [ "$attempts" -gt 0 ]; do
    if compose exec -T ollama ollama list >/dev/null 2>&1; then
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 2
  done
  echo "Ollama did not become ready in time." >&2
  return 1
}

case "${1:-}" in
  up)
    mkdir -p "$PROJECT_DIR/reference-docs"
    compose up -d ollama qdrant
    wait_for_ollama
    compose exec -T ollama ollama pull "$LLM_MODEL"
    compose exec -T ollama ollama pull "$EMBEDDING_MODEL"
    compose up -d --build api web
    "$PROJECT_DIR/scripts/smoke.sh"
    echo "TerraRAG is available at http://127.0.0.1:3000"
    ;;
  down)
    compose down
    ;;
  status)
    compose ps
    ;;
  *)
    echo "Usage: $0 {up|down|status}" >&2
    exit 2
    ;;
esac

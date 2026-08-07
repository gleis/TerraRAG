#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ACTION=${1:-}
RUNTIME=${TERRARAG_RUNTIME:-auto}

case "$ACTION" in
  up|down|status) ;;
  *)
    echo "Usage: $0 {up|down|status}" >&2
    exit 2
    ;;
esac

if [ "$RUNTIME" = "auto" ]; then
  if command -v container >/dev/null 2>&1 && container system status >/dev/null 2>&1; then
    RUNTIME=apple
  elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    RUNTIME=docker
  elif command -v podman >/dev/null 2>&1 && podman info >/dev/null 2>&1 && { podman compose version >/dev/null 2>&1 || command -v podman-compose >/dev/null 2>&1; }; then
    RUNTIME=podman
  else
    echo "No supported container runtime is ready. Install Docker Compose, Podman Compose, or start an available container service." >&2
    exit 1
  fi
fi

case "$RUNTIME" in
  apple)
    exec "$PROJECT_DIR/scripts/apple-$ACTION.sh"
    ;;
  docker|podman)
    export TERRARAG_RUNTIME="$RUNTIME"
    exec "$PROJECT_DIR/scripts/compose-runtime.sh" "$ACTION"
    ;;
  *)
    echo "Unsupported TERRARAG_RUNTIME '$RUNTIME'. Use docker, podman, or apple." >&2
    exit 2
    ;;
esac

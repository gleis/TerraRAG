#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
REPOSITORY_MOUNT=${HOST_REPOSITORY_ROOT:-$PROJECT_DIR}
LLM_MODEL=${LLM_MODEL:-gemma4:latest}
EMBEDDING_MODEL=${EMBEDDING_MODEL:-qwen3-embedding:0.6b}

if ! container system status >/dev/null 2>&1; then
  echo "Apple container service is not running. Run: container system start" >&2
  exit 1
fi

if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null; then
  echo "Native Ollama is not responding on 127.0.0.1:11434." >&2
  exit 1
fi

if ! ollama list | awk 'NR > 1 {print $1}' | grep -Fx "$LLM_MODEL" >/dev/null; then
  echo "Missing generation model: $LLM_MODEL" >&2
  exit 1
fi

if ! ollama list | awk 'NR > 1 {print $1}' | grep -Fx "$EMBEDDING_MODEL" >/dev/null; then
  echo "Missing embedding model: $EMBEDDING_MODEL" >&2
  echo "Install it with: ollama pull $EMBEDDING_MODEL" >&2
  exit 1
fi

if ! container run --rm docker.io/curlimages/curl:latest \
  -fsS http://host.container.internal:11434/api/version >/dev/null; then
  echo "The Apple container host bridge is unavailable." >&2
  echo "Repair it with: sudo container system dns create host.container.internal --localhost 203.0.113.113" >&2
  exit 1
fi

mkdir -p "$PROJECT_DIR/data/qdrant" "$PROJECT_DIR/data/api" "$PROJECT_DIR/reference-docs"
chmod 700 "$PROJECT_DIR/data/qdrant" "$PROJECT_DIR/data/api"

"$PROJECT_DIR/scripts/apple-down.sh"

container build --tag terrarag-api:dev "$PROJECT_DIR/backend"
container build \
  --build-arg NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 \
  --tag terrarag-web:dev "$PROJECT_DIR/web"

container run --detach --name terrarag-qdrant \
  --cpus 2 --memory 2g \
  --publish 127.0.0.1:6333:6333 \
  --volume "$PROJECT_DIR/data/qdrant:/qdrant/storage" \
  docker.io/qdrant/qdrant:v1.20.0

container run --detach --name terrarag-api \
  --cpus 4 --memory 4g \
  --user "$(id -u):$(id -g)" \
  --publish 127.0.0.1:8000:8000 \
  --volume "$PROJECT_DIR/data/api:/data" \
  --mount "type=bind,source=$REPOSITORY_MOUNT,target=/repos,readonly" \
  --mount "type=bind,source=$PROJECT_DIR/reference-docs,target=/repos/reference-docs,readonly" \
  --env "LLM_MODEL=$LLM_MODEL" \
  --env "EMBEDDING_MODEL=$EMBEDDING_MODEL" \
  --env OLLAMA_URL=http://host.container.internal:11434 \
  --env QDRANT_URL=http://host.container.internal:6333 \
  --env SQLITE_PATH=/data/terrarag.sqlite3 \
  --env REPOSITORY_ROOT=/repos \
  terrarag-api:dev

container run --detach --name terrarag-web \
  --cpus 2 --memory 1g \
  --publish 127.0.0.1:3000:3000 \
  terrarag-web:dev

"$PROJECT_DIR/scripts/smoke.sh"
echo "TerraRAG is available at http://127.0.0.1:3000"

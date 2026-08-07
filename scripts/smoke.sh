#!/bin/sh
set -eu

API_URL=${API_URL:-http://127.0.0.1:8000}
WEB_URL=${WEB_URL:-http://127.0.0.1:3000}
QDRANT_URL=${QDRANT_URL:-http://127.0.0.1:6333}

probe() {
  label=$1
  url=$2
  attempts=30
  while [ "$attempts" -gt 0 ]; do
    if curl -fsS "$url" >/dev/null; then
      echo "$label: ok"
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 1
  done
  echo "$label: failed ($url)" >&2
  return 1
}

probe qdrant "$QDRANT_URL/healthz"
probe api "$API_URL/health/live"
probe web "$WEB_URL"

echo "TerraRAG runtime smoke test passed."

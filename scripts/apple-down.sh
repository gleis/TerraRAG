#!/bin/sh
set -eu

for service in terrarag-web terrarag-api terrarag-qdrant; do
  container stop "$service" >/dev/null 2>&1 || true
  container delete "$service" >/dev/null 2>&1 || true
done

echo "TerraRAG Apple containers stopped."

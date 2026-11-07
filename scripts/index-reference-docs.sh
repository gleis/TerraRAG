#!/bin/sh
set -eu

API_URL=${API_URL:-http://127.0.0.1:8000}

repository=$(curl -fsS -X POST "$API_URL/repositories" \
  -H 'Content-Type: application/json' \
  -d '{"path":"reference-docs","name":"Official Terraform v1.17.x + Terragrunt v1.2.1 Docs"}')
repository_id=$(printf '%s' "$repository" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

echo "Indexing official reference corpus as $repository_id ..."
result=$(curl -fsS -X POST "$API_URL/repositories/$repository_id/index")
printf '%s' "$result" | python3 -c 'import json,sys; item=json.load(sys.stdin); print("Indexed {} files, {} chunks, status={}".format(item["file_count"], item["chunk_count"], item["status"]))'

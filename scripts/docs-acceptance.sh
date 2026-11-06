#!/bin/sh
set -eu

API_URL=${API_URL:-http://127.0.0.1:8000}

repositories=$(curl -fsS "$API_URL/repositories")
repository_id=$(printf '%s' "$repositories" | python3 -c 'import json,sys; items=json.load(sys.stdin); print(next(item["id"] for item in items if item["root_path"] == "reference-docs" and item["status"] == "ready"))')

repository=$(curl -fsS "$API_URL/repositories/$repository_id")
printf '%s' "$repository" | python3 -c 'import json,sys; item=json.load(sys.stdin); assert item["file_count"] >= 379; assert item["chunk_count"] >= 3500'

search=$(curl -fsS -X POST "$API_URL/search" -H 'Content-Type: application/json' \
  -d "{\"repository_id\":\"$repository_id\",\"query\":\"Terraform lifecycle prevent_destroy\",\"limit\":5}")
printf '%s' "$search" | python3 -c 'import json,sys; item=json.load(sys.stdin); top=item["sources"][0]; assert top["metadata"]["corpus"] == "official_docs"; assert top["metadata"]["product"] == "Terraform"; assert top["metadata"]["version"] == "v1.17.x"; assert "prevent_destroy" in top["content"]'

terragrunt=$(curl -fsS -X POST "$API_URL/search" -H 'Content-Type: application/json' \
  -d "{\"repository_id\":\"$repository_id\",\"query\":\"Terragrunt dependency block mock_outputs outputs\",\"limit\":5}")
printf '%s' "$terragrunt" | python3 -c 'import json,sys; item=json.load(sys.stdin); top=item["sources"][0]; assert top["metadata"]["product"] == "Terragrunt"; assert top["metadata"]["version"] == "v1.2.1"; assert "dependency" in top["content"]'

chat=$(curl -fsS -X POST "$API_URL/chat" -H 'Content-Type: application/json' \
  -d "{\"repository_id\":\"$repository_id\",\"question\":\"What does Terraform lifecycle prevent_destroy do?\"}")
printf '%s' "$chat" | python3 -c 'import json,sys; item=json.load(sys.stdin); assert "prevent_destroy" in item["answer"]; assert "[file:terraform/v1.17.x/" in item["answer"]; assert item["sources"]'

echo "TerraRAG official documentation acceptance passed."

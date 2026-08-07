#!/bin/sh
set -eu

API_URL=${API_URL:-http://127.0.0.1:8000}

health=$(curl -fsS "$API_URL/health")
printf '%s' "$health" | python3 -c 'import json,sys; assert json.load(sys.stdin)["status"] == "ready"'

repositories=$(curl -fsS "$API_URL/repositories")
repository_id=$(printf '%s' "$repositories" | python3 -c 'import json,sys; items=json.load(sys.stdin); print(next(item["id"] for item in items if item["root_path"] == "example-infra"))')

index_result=$(curl -fsS -X POST "$API_URL/repositories/$repository_id/index")
printf '%s' "$index_result" | python3 -c 'import json,sys; item=json.load(sys.stdin); assert item["status"] == "ready"; assert item["file_count"] == 7; assert item["chunk_count"] >= 25; assert item["edge_count"] >= 15'

files=$(curl -fsS "$API_URL/repositories/$repository_id/files")
printf '%s' "$files" | python3 -c 'import json,sys; paths=[item["path"] for item in json.load(sys.stdin)]; assert not any("credential" in path or ".tfstate" in path or ".env" in path for path in paths)'

search=$(curl -fsS -X POST "$API_URL/search" -H 'Content-Type: application/json' -d "{\"repository_id\":\"$repository_id\",\"query\":\"aws_instance.worker\",\"limit\":5}")
printf '%s' "$search" | python3 -c 'import json,sys; item=json.load(sys.stdin); assert item["sources"][0]["address"] == "aws_instance.worker"; assert item["sources"][0]["start_line"] == 21'

graph=$(curl -fsS "$API_URL/repositories/$repository_id/graph")
printf '%s' "$graph" | python3 -c 'import json,sys; relationships={item["relationship"] for item in json.load(sys.stdin)}; assert {"references","includes","dependency","feeds_from","terraform_source"} <= relationships'

chat=$(curl -fsS -X POST "$API_URL/chat" -H 'Content-Type: application/json' -d "{\"repository_id\":\"$repository_id\",\"question\":\"Where does prod set instance_type?\"}")
printf '%s' "$chat" | python3 -c 'import json,sys; item=json.load(sys.stdin); assert "m7g.large" in item["answer"]; assert "[file:live/prod/us-east-1/app/terragrunt.hcl lines 14-20]" in item["answer"]; assert item["sources"]'

echo "TerraRAG end-to-end acceptance passed."

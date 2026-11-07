#!/usr/bin/env bash
# Exercise the rebuilt TLS implementation and storage across container replacement.
set -euo pipefail
stage=$(mktemp -d)
name=qdrant-tls-check
volume=qdrant-tls-review-storage
cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
  rm -rf "$stage"
}
trap cleanup EXIT
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost \
  -addext subjectAltName=IP:127.0.0.1,DNS:localhost \
  -keyout "$stage/key.pem" -out "$stage/cert.pem" 2>/dev/null
docker volume create "$volume" >/dev/null
start_server() {
  docker run -d --name "$name" -p 127.0.0.1:16333:6333 \
    -v "$stage:/tls:ro" -v "$volume:/qdrant/storage" \
    -e QDRANT__SERVICE__ENABLE_TLS=true \
    -e QDRANT__TLS__CERT=/tls/cert.pem -e QDRANT__TLS__KEY=/tls/key.pem \
    terrarag-qdrant:review >/dev/null
  for _ in $(seq 1 60); do
    if curl -fsS --cacert "$stage/cert.pem" https://127.0.0.1:16333/healthz >/dev/null; then return; fi
    sleep 1
  done
  docker logs "$name"
  return 1
}
start_server
if curl -fsS --max-time 5 https://127.0.0.1:16333/healthz >/dev/null 2>&1; then
  echo 'Unexpectedly accepted an untrusted TLS certificate' >&2; exit 1
fi
if curl -fsS --max-time 5 http://127.0.0.1:16333/healthz >/dev/null 2>&1; then
  echo 'Unexpectedly served plaintext while TLS is required' >&2; exit 1
fi
curl -fsS --cacert "$stage/cert.pem" -X PUT https://127.0.0.1:16333/collections/persisted \
  -H 'Content-Type: application/json' -d '{"vectors":{"size":2,"distance":"Cosine"}}'
curl -fsS --cacert "$stage/cert.pem" -X PUT 'https://127.0.0.1:16333/collections/persisted/points?wait=true' \
  -H 'Content-Type: application/json' -d '{"points":[{"id":1,"vector":[1,0]}]}'
docker stop "$name" >/dev/null
docker rm "$name" >/dev/null
start_server
curl -fsS --cacert "$stage/cert.pem" -X POST https://127.0.0.1:16333/collections/persisted/points/query \
  -H 'Content-Type: application/json' -d '{"query":[1,0]}' \
  | python3 -c 'import json,sys; assert json.load(sys.stdin)["result"]["points"][0]["id"] == 1'
echo 'Qdrant trusted TLS, certificate rejection and replacement-persistence checks passed'

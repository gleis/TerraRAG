#!/bin/sh
set -eu

container system status
container list --all
echo
curl -fsS http://127.0.0.1:11434/api/version || true

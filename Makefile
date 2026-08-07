.PHONY: up down status apple-up apple-down apple-status docs-sync docs-index docs-refresh docs-acceptance smoke acceptance test

up:
	./scripts/runtime.sh up

down:
	./scripts/runtime.sh down

status:
	./scripts/runtime.sh status

apple-up:
	./scripts/apple-up.sh

apple-down:
	./scripts/apple-down.sh

apple-status:
	./scripts/apple-status.sh

docs-sync:
	./scripts/sync-reference-docs.sh

docs-index:
	./scripts/index-reference-docs.sh

docs-refresh: docs-sync docs-index

docs-acceptance:
	./scripts/docs-acceptance.sh

smoke:
	./scripts/smoke.sh

acceptance:
	./scripts/acceptance.sh

test:
	cd backend && python -m pytest

# TerraRAG

TerraRAG is a private, local-first knowledge assistant for Terraform and Terragrunt repositories. The MVP includes Tree-sitter HCL parsing with exact lines, Terragrunt relationship extraction, incremental Ollama embeddings, Qdrant semantic search, SQLite FTS5 and structural edges, grounded local generation, clickable citations, a source viewer, and a RAG inspector.

The detailed delivery sequence is in [BUILD_PLAN.md](BUILD_PLAN.md). The product requirements are in `TerraRAG_Terraform_Terragrunt_Developer_Spec.pdf`.

## Vader - Apple containers

Prerequisites already configured on `vader`:

- Apple `container` 1.2.0
- native Ollama on `127.0.0.1:11434`
- `gemma4:latest` generation model
- `qwen3-embedding:0.6b` embedding model
- `host.container.internal` localhost bridge

Start or rebuild the complete stack:

```sh
make apple-up
```

Then open:

- UI: <http://127.0.0.1:3000>
- API docs: <http://127.0.0.1:8000/docs>
- aggregate readiness: <http://127.0.0.1:8000/health>
- Qdrant: <http://127.0.0.1:6333/dashboard>

The included `example-infra` repository is already registered and indexed on Vader. Try these questions:

- Where does prod set `instance_type`?
- Where does the app get its VPC ID?
- How does dev differ from prod?
- Explain the production architecture.

### Official reference documentation

TerraRAG can maintain a separately selectable, version-pinned corpus of official Terraform and Terragrunt documentation. The current pins are Terraform language docs `v1.15.x` and Terragrunt docs `v1.1.2`.

Download the pinned upstream Markdown/MDX sources and index them while the stack is running:

```sh
make docs-refresh
```

The downloaded corpus is local runtime data under `reference-docs/` and is not committed. The UI labels it as official, version-pinned, and read-only. Select **Official Terraform v1.15.x + Terragrunt v1.1.2 Docs** to ask reference questions; select a repository for questions about the repository's actual configuration.

Refreshes fail closed if an upstream commit no longer matches the reviewed pin. Update the commit constants in `scripts/sync-reference-docs.sh` only after reviewing upstream changes.

To index another repository, mount a broader host directory by setting `HOST_REPOSITORY_ROOT` before `make apple-up`, then register a path below `/repos` in the UI. Source mounts are read-only.

Operational commands:

```sh
make apple-status
make smoke
make acceptance
make docs-acceptance
make apple-down
```

After a macOS restart, recreate the host bridge if the startup check requests it:

```sh
sudo container system dns create host.container.internal --localhost 203.0.113.113
```

## Local checks

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest -q

cd ../web
npm ci
npm audit --audit-level=high
npm run build
```

## Privacy boundary

Ollama remains a native host service for Apple GPU acceleration. Application containers reach it only through the configured localhost bridge. Published application ports bind to `127.0.0.1`, repository mounts are read-only, and cloud AI is disabled in the default configuration.

## Implemented API

- `POST /repositories` and `POST /repositories/{id}/index`
- `GET /repositories`, `/repositories/{id}`, `/files`, `/source`, and `/graph`
- `POST /search` for raw hybrid retrieval
- `POST /chat` for local grounded generation
- `GET /chunks/{id}` and `GET /health`

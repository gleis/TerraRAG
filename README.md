# TerraRAG

TerraRAG is a private, local-first knowledge assistant for Terraform and Terragrunt repositories. It combines exact HCL parsing, Terragrunt relationship extraction, Ollama embeddings and generation, Qdrant semantic search, SQLite full-text search, clickable citations, a source viewer, and a retrieval inspector.

## Quick start

Install these prerequisites:

- Git, `make`, and `curl`
- A supported container runtime: Docker Compose, Podman Compose, or Apple containers
- At least 8 GB of free memory and enough disk space for the selected Ollama models

Clone and start TerraRAG:

```sh
git clone https://github.com/gleis/TerraRAG.git
cd TerraRAG
make up
```

`make up` detects an available runtime, builds the application, starts its services, downloads the configured local models when necessary, and runs a smoke test. The first start takes longer because container images and models must be downloaded.

Open:

- UI: <http://127.0.0.1:3000>
- API documentation: <http://127.0.0.1:8000/docs>
- Readiness report: <http://127.0.0.1:8000/health>
- Qdrant dashboard: <http://127.0.0.1:6333/dashboard>

Useful commands:

```sh
make status
make smoke
make acceptance
make down
```

If more than one runtime is installed, select one explicitly:

```sh
TERRARAG_RUNTIME=docker make up
TERRARAG_RUNTIME=podman make up
TERRARAG_RUNTIME=apple make up
```

## Index a repository

By default, the TerraRAG project directory is mounted read-only at `/repos`, so the included `example-infra` directory is immediately available. In the UI:

1. Enter `example-infra` under **Path below /repos**.
2. Select **Register path**.
3. Select **Build index**.
4. Ask a question, such as `Where does prod set instance_type?`.

To make other repositories available, mount their common parent directory when starting TerraRAG:

```sh
HOST_REPOSITORY_ROOT=/absolute/path/to/projects make up
```

Then register a repository using its path relative to that directory. Source mounts are read-only, paths cannot escape `/repos`, and common secret and state files are excluded from indexing.

## Official Terraform and Terragrunt documentation

TerraRAG can maintain a separate, selectable corpus of version-pinned official documentation. With the application running:

```sh
make docs-refresh
```

This downloads the reviewed Terraform `v1.15.x` and Terragrunt `v1.1.2` documentation into the ignored `reference-docs/` runtime directory and indexes it. Select **Official Terraform v1.15.x + Terragrunt v1.1.2 Docs** in the UI for product-reference questions.

Refreshes fail closed if an upstream commit no longer matches the reviewed pin. Update the commit constants in `scripts/sync-reference-docs.sh` only after reviewing upstream changes.

Validate both example corpora with:

```sh
make acceptance
make docs-acceptance
```

## Configuration

The defaults run without a configuration file. Override settings through environment variables when needed:

```sh
LLM_MODEL=gemma4:latest \
EMBEDDING_MODEL=qwen3-embedding:0.6b \
HOST_REPOSITORY_ROOT=/absolute/path/to/projects \
make up
```

Compose users can copy `deploy/env.example` to `deploy/.env` for persistent overrides. `NEXT_PUBLIC_API_URL` is compiled into the web image, so rebuild with `make up` after changing it.

## Local development and checks

Run the backend tests:

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest -q
```

Build the web interface:

```sh
cd web
npm ci
npm run build
```

## Privacy boundary

All retrieval, embeddings, and generation run locally. Application ports bind to `127.0.0.1`, repository mounts are read-only, cloud AI is disabled by default, and indexed data remains in local container volumes. Review any repository before indexing it and keep credentials, state files, and other sensitive material outside the mounted root when possible.

## API

- `POST /repositories` and `POST /repositories/{id}/index`
- `GET /repositories`, `/repositories/{id}`, `/files`, `/source`, and `/graph`
- `POST /search` for raw hybrid retrieval
- `POST /chat` for locally generated, evidence-grounded answers
- `GET /chunks/{id}` and `GET /health`

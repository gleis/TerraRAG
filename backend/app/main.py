import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.ingestion import UnsafeRepository, parse_repository, resolve_repository
from app.models import ChatRequest, RepositoryCreate, SearchRequest
from app.rag import LocalAI, QdrantStore, retrieve
from app.storage import Storage


@lru_cache
def get_storage() -> Storage:
    return Storage(get_settings().sqlite_path)


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_storage()
    yield


app = FastAPI(
    title="TerraRAG API",
    version="0.2.0",
    description="Local-first Terraform and Terragrunt retrieval API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


async def probe(url: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            try:
                body = response.json()
            except ValueError:
                body = {"text": response.text.strip()}
            return True, body, None
    except Exception as exc:
        return False, None, str(exc)


def require_repository(repository_id: str) -> dict[str, Any]:
    repository = get_storage().get_repository(repository_id)
    if not repository:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repository


def public_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        key: chunk.get(key)
        for key in (
            "id", "file_path", "language", "object_type", "object_name", "address",
            "start_line", "end_line", "content", "metadata", "score", "methods",
        )
    }


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "TerraRAG", "docs": "/docs", "health": "/health"}


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    qdrant_ok, qdrant_body, qdrant_error = await probe(f"{settings.qdrant_url.rstrip('/')}/healthz")
    ollama_ok, ollama_body, ollama_error = await probe(f"{settings.ollama_url.rstrip('/')}/api/tags")
    available_models = {item.get("name") for item in (ollama_body or {}).get("models", [])}
    models = {
        "generation": {"name": settings.llm_model, "available": settings.llm_model in available_models},
        "embedding": {"name": settings.embedding_model, "available": settings.embedding_model in available_models},
    }
    ready = qdrant_ok and ollama_ok and all(item["available"] for item in models.values())
    return {
        "status": "ready" if ready else "degraded",
        "checked_at": datetime.now(UTC).isoformat(),
        "services": {
            "api": {"ok": True},
            "qdrant": {"ok": qdrant_ok, "response": qdrant_body, "error": qdrant_error},
            "ollama": {"ok": ollama_ok, "error": ollama_error},
        },
        "models": models,
        "privacy": {
            "cloud_ai_enabled": False,
            "repository_root": str(settings.repository_root),
            "debug_chunk_logging": settings.debug_log_chunks,
        },
    }


@app.post("/repositories", status_code=201)
async def create_repository(body: RepositoryCreate) -> dict[str, Any]:
    settings = get_settings()
    try:
        resolved = resolve_repository(settings.repository_root, body.path)
    except (UnsafeRepository, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    root = settings.repository_root.resolve()
    relative = "." if resolved == root else resolved.relative_to(root).as_posix()
    existing = get_storage().get_repository_by_path(relative)
    if existing:
        return existing
    repository_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"terrarag:{resolved}"))
    return get_storage().create_repository(repository_id, body.name or resolved.name, relative)


@app.get("/repositories")
async def repositories() -> list[dict[str, Any]]:
    return get_storage().list_repositories()


@app.get("/repositories/{repository_id}")
async def repository(repository_id: str) -> dict[str, Any]:
    return require_repository(repository_id)


@app.post("/repositories/{repository_id}/index")
async def index_repository(repository_id: str) -> dict[str, Any]:
    repository = require_repository(repository_id)
    settings = get_settings()
    storage = get_storage()
    storage.set_status(repository_id, "indexing")
    try:
        root = resolve_repository(settings.repository_root, repository["root_path"])
        files, chunks, edges = parse_repository(root)
        if not chunks:
            raise ValueError("No indexable files were found")
        local_ai = LocalAI(settings)
        cached = storage.cached_embeddings(chunks, settings.embedding_model)
        missing = [chunk for chunk in chunks if chunk["id"] not in cached]
        for start in range(0, len(missing), 32):
            batch = missing[start:start + 32]
            vectors = await local_ai.embeddings([item["embedding_text"] for item in batch])
            storage.cache_embeddings(batch, settings.embedding_model, vectors)
            cached.update({chunk["id"]: vector for chunk, vector in zip(batch, vectors, strict=True)})
        vectors = [cached[chunk["id"]] for chunk in chunks]
        await QdrantStore(settings).replace_repository(repository_id, chunks, vectors)
        generation = str(uuid.uuid4())
        storage.replace_index(repository_id, generation, files, chunks, edges, datetime.now(UTC).isoformat())
        result = require_repository(repository_id)
        result["indexing"] = {"embedded": len(missing), "reused": len(chunks) - len(missing)}
        return result
    except Exception as exc:
        storage.set_status(repository_id, "failed", str(exc))
        raise HTTPException(status_code=500, detail=f"Indexing failed: {exc}") from exc


@app.get("/repositories/{repository_id}/files")
async def repository_files(repository_id: str) -> list[dict[str, Any]]:
    require_repository(repository_id)
    return get_storage().files(repository_id)


@app.get("/repositories/{repository_id}/source")
async def repository_source(repository_id: str, path: str = Query(min_length=1)) -> dict[str, Any]:
    require_repository(repository_id)
    source = get_storage().source(repository_id, path)
    if not source:
        raise HTTPException(status_code=404, detail="Indexed source not found")
    return source


@app.get("/repositories/{repository_id}/graph")
async def repository_graph(repository_id: str) -> list[dict[str, Any]]:
    require_repository(repository_id)
    return get_storage().graph(repository_id)


@app.get("/chunks/{chunk_id}")
async def chunk(chunk_id: str) -> dict[str, Any]:
    result = get_storage().chunk(chunk_id)
    if not result:
        raise HTTPException(status_code=404, detail="Chunk not found")
    return public_chunk(result)


@app.post("/search")
async def search(body: SearchRequest) -> dict[str, Any]:
    require_repository(body.repository_id)
    chunks, metrics = await retrieve(get_settings(), get_storage(), body.repository_id, body.query, body.limit)
    return {"query": body.query, "sources": [public_chunk(item) for item in chunks], "retrieval": metrics}


@app.post("/chat")
async def chat(body: ChatRequest) -> dict[str, Any]:
    require_repository(body.repository_id)
    settings = get_settings()
    chunks, metrics = await retrieve(settings, get_storage(), body.repository_id, body.question, 8)
    if not chunks:
        return {
            "answer": "I cannot determine that from the indexed repository evidence.",
            "sources": [], "retrieval": metrics, "model": settings.llm_model,
        }
    answer, model = await LocalAI(settings).answer(body.question, chunks)
    return {
        "answer": answer,
        "sources": [public_chunk(item) for item in chunks],
        "retrieval": metrics,
        "model": model,
    }

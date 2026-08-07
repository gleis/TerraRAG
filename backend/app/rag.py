import re
from collections import defaultdict
from typing import Any

import httpx

from app.config import Settings
from app.storage import Storage


TEACHING_SYSTEM_PROMPT = """You are TerraRAG, a local technical tutor for Terraform and Terragrunt repositories and official reference documentation.
Use only the supplied selected-corpus evidence. Never invent files, values, resources, modules, relationships, examples, or documented behavior.
Treat corpus=official_docs as product documentation and state its product/version when that qualification matters.
Distinguish what exists, what can be inferred, and what you recommend. If evidence is insufficient, say so.

Teach the answer in this order, using these Markdown headings when the evidence supports them:
### Direct answer
Give the conclusion first in plain language.
### How it works
Explain the mechanism and connect it to the user's question step by step.
### Example
Provide a small, focused HCL example derived from the evidence. For repository questions, label examples as either "From this repository" or "Illustrative" and never imply invented configuration exists in the repository. Omit the example if the evidence cannot support one safely.
### When to use it
Explain the practical use case, tradeoffs, and important caveats.
### Check your understanding
End with one short question the learner can answer from the explanation.

Prefer concrete explanations over jargon. Define specialized terms on first use. Keep code examples minimal and valid-looking, inside fenced hcl blocks.
Cite every factual paragraph and every example using the exact citation labels supplied, such as [file:path lines X-Y]."""


class LocalAI:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def embeddings(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.settings.ollama_url.rstrip('/')}/api/embed",
                json={"model": self.settings.embedding_model, "input": texts, "truncate": True},
            )
            response.raise_for_status()
            return response.json()["embeddings"]

    async def answer(self, question: str, evidence: list[dict[str, Any]]) -> tuple[str, str]:
        blocks = "\n\n".join(
            f"SOURCE {index + 1}: [file:{item['file_path']} lines {item['start_line']}-{item['end_line']}]\n"
            f"PROVENANCE: corpus={item.get('metadata', {}).get('corpus', 'repository')} "
            f"product={item.get('metadata', {}).get('product') or 'repository'} "
            f"version={item.get('metadata', {}).get('version') or 'unversioned'}\n{item['content']}"
            for index, item in enumerate(evidence)
        )
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{self.settings.ollama_url.rstrip('/')}/api/chat",
                json={
                    "model": self.settings.llm_model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": TEACHING_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Question: {question}\n\nSelected corpus evidence:\n{blocks}"},
                    ],
                    "options": {"temperature": 0.1},
                },
            )
            response.raise_for_status()
            body = response.json()
        answer = body.get("message", {}).get("content", "").strip()
        if evidence and "[file:" not in answer:
            citations = "\n".join(
                f"- [file:{item['file_path']} lines {item['start_line']}-{item['end_line']}]"
                for item in evidence[:4]
            )
            answer = f"{answer}\n\nEvidence:\n{citations}"
        return answer, body.get("model", self.settings.llm_model)


class QdrantStore:
    def __init__(self, settings: Settings):
        self.base = settings.qdrant_url.rstrip("/")
        safe_model = re.sub(r"[^a-z0-9]+", "_", settings.embedding_model.lower()).strip("_")
        self.collection = f"terrarag_{safe_model}"[:63]

    async def ensure(self, vector_size: int) -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base}/collections/{self.collection}")
            if response.status_code == 404:
                created = await client.put(
                    f"{self.base}/collections/{self.collection}",
                    json={"vectors": {"size": vector_size, "distance": "Cosine"}},
                )
                created.raise_for_status()
            else:
                response.raise_for_status()

    async def replace_repository(self, repository_id: str, chunks: list[dict[str, Any]], vectors: list[list[float]]) -> None:
        if not vectors:
            return
        await self.ensure(len(vectors[0]))
        async with httpx.AsyncClient(timeout=120.0) as client:
            deleted = await client.post(
                f"{self.base}/collections/{self.collection}/points/delete?wait=true",
                json={"filter": {"must": [{"key": "repository_id", "match": {"value": repository_id}}]}},
            )
            deleted.raise_for_status()
            for start in range(0, len(chunks), 64):
                points = []
                for chunk, vector in zip(chunks[start:start + 64], vectors[start:start + 64], strict=True):
                    points.append({
                        "id": chunk["id"], "vector": vector,
                        "payload": {
                            "repository_id": repository_id, "file_path": chunk["file_path"],
                            "object_type": chunk["object_type"], "address": chunk.get("address"),
                            "start_line": chunk["start_line"], "end_line": chunk["end_line"],
                        },
                    })
                response = await client.put(
                    f"{self.base}/collections/{self.collection}/points?wait=true",
                    json={"points": points},
                )
                response.raise_for_status()

    async def search(self, repository_id: str, vector: list[float], limit: int) -> list[tuple[str, float]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base}/collections/{self.collection}/points/query",
                json={
                    "query": vector,
                    "filter": {"must": [{"key": "repository_id", "match": {"value": repository_id}}]},
                    "limit": limit,
                    "with_payload": True,
                },
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            points = response.json().get("result", {}).get("points", [])
            return [(str(point["id"]), float(point["score"])) for point in points]


async def retrieve(settings: Settings, storage: Storage, repository_id: str, query: str, limit: int = 8) -> tuple[list[dict[str, Any]], dict[str, int]]:
    exact = storage.exact_search(repository_id, query, 12)
    lexical = storage.lexical_search(repository_id, query, 20)
    query_vector = (await LocalAI(settings).embeddings([query]))[0]
    semantic = await QdrantStore(settings).search(repository_id, query_vector, 20)

    scores: dict[str, float] = defaultdict(float)
    methods: dict[str, list[str]] = defaultdict(list)
    for method, results, weight in (("exact", exact, 2.0), ("keyword", lexical, 1.2), ("semantic", semantic, 1.0)):
        for rank, (chunk_id, _) in enumerate(results, start=1):
            scores[chunk_id] += weight / (60 + rank)
            methods[chunk_id].append(method)
    seeds = [item for item, _ in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:6]]
    related = storage.related_chunks(repository_id, seeds)
    for rank, chunk_id in enumerate(related, start=1):
        scores[chunk_id] += 0.8 / (60 + rank)
        methods[chunk_id].append("structural")

    # A deterministic domain-aware pass keeps important exact configuration evidence
    # ahead of broad semantic matches (for example, `vpc_id` inputs ahead of a generic
    # variable declaration). It operates only on already-retrieved candidates.
    words = [word for word in re.findall(r"[a-z0-9]+", query.lower()) if word not in {"the", "a", "an", "is", "are", "does", "do", "where", "what", "which", "how", "its", "from", "to"}]
    variants = set(words)
    variants.update(f"{left}_{right}" for left, right in zip(words, words[1:]))
    candidate_rows = storage.chunks(list(scores))
    for row in candidate_rows:
        haystack = f"{row['file_path']}\n{row.get('address') or ''}\n{row['content']}".lower()
        hits = sum(1 for term in variants if term in haystack)
        if hits:
            scores[row["id"]] += min(hits, 4) * 0.006
            methods[row["id"]].append("domain")
        environment = row.get("metadata", {}).get("environment")
        if environment and environment.lower() in words:
            scores[row["id"]] += 0.02
        if row["object_type"] == "inputs" and any(word in query.lower() for word in ("set", "get", "input", "override", "differ")):
            scores[row["id"]] += 0.012
    ordered = [item for item, _ in sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:limit]]
    chunks = storage.chunks(ordered)
    for chunk in chunks:
        chunk["score"] = round(scores[chunk["id"]], 6)
        chunk["methods"] = methods[chunk["id"]]
    return chunks, {
        "semantic_candidates": len(semantic), "keyword_hits": len(lexical),
        "exact_hits": len(exact), "structural_edges_used": len(related), "chunks_used": len(chunks),
    }

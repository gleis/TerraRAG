from pathlib import Path

from app.ingestion import parse_repository
from app.storage import Storage


EXAMPLE = Path(__file__).parents[2] / "example-infra"


def test_storage_exact_and_lexical_search(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "test.sqlite3")
    storage.create_repository("repo", "Example", "example-infra")
    files, chunks, edges = parse_repository(EXAMPLE)
    storage.replace_index("repo", "generation", files, chunks, edges, "now")

    exact = storage.exact_search("repo", "aws_instance.worker", 10)
    lexical = storage.lexical_search("repo", "instance_type", 10)

    assert chunks
    assert exact
    assert lexical
    assert storage.get_repository("repo")["status"] == "ready"


def test_embedding_cache_reuses_unchanged_chunks(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "test.sqlite3")
    _, chunks, _ = parse_repository(EXAMPLE)
    sample = chunks[:2]
    vectors = [[0.1, 0.2], [0.3, 0.4]]

    storage.cache_embeddings(sample, "embedding-model", vectors)

    assert storage.cached_embeddings(sample, "embedding-model") == {
        sample[0]["id"]: vectors[0],
        sample[1]["id"]: vectors[1],
    }
    changed = [{**sample[0], "embedding_text": sample[0]["embedding_text"] + " changed"}]
    assert storage.cached_embeddings(changed, "embedding-model") == {}


def test_reindex_removes_stale_chunks(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "test.sqlite3")
    storage.create_repository("repo", "Example", "example-infra")
    files, chunks, edges = parse_repository(EXAMPLE)
    removed = chunks[0]
    storage.replace_index("repo", "first", files, chunks, edges, "now")

    remaining = [chunk for chunk in chunks if chunk["id"] != removed["id"]]
    remaining_edges = [edge for edge in edges if edge["source_chunk_id"] != removed["id"] and edge.get("target_chunk_id") != removed["id"]]
    storage.replace_index("repo", "second", files, remaining, remaining_edges, "later")

    assert storage.chunk(removed["id"]) is None
    assert storage.get_repository("repo")["chunk_count"] == len(remaining)

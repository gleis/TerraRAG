import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS repositories (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  root_path TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'registered',
  generation TEXT,
  file_count INTEGER NOT NULL DEFAULT 0,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  edge_count INTEGER NOT NULL DEFAULT 0,
  indexed_at TEXT,
  error TEXT
);
CREATE TABLE IF NOT EXISTS files (
  repository_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  content TEXT NOT NULL,
  language TEXT NOT NULL,
  PRIMARY KEY(repository_id, path)
);
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  repository_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
  file_path TEXT NOT NULL,
  language TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_name TEXT,
  address TEXT,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding_text TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  generation TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_repo_idx ON chunks(repository_id);
CREATE INDEX IF NOT EXISTS chunks_address_idx ON chunks(repository_id, address);
CREATE TABLE IF NOT EXISTS edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  repository_id TEXT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
  source_chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
  relationship TEXT NOT NULL,
  target TEXT NOT NULL,
  target_chunk_id TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS edges_repo_idx ON edges(repository_id);
CREATE TABLE IF NOT EXISTS embedding_cache (
  chunk_id TEXT NOT NULL,
  model TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  vector_json TEXT NOT NULL,
  PRIMARY KEY(chunk_id, model)
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  chunk_id UNINDEXED,
  repository_id UNINDEXED,
  file_path,
  address,
  object_name,
  content,
  tokenize='unicode61 tokenchars ''._-'''
);
"""


class Storage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row else None

    def list_repositories(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM repositories ORDER BY name")]

    def get_repository(self, repository_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            return self.row(db.execute("SELECT * FROM repositories WHERE id=?", (repository_id,)).fetchone())

    def get_repository_by_path(self, root_path: str) -> dict[str, Any] | None:
        with self.connect() as db:
            return self.row(db.execute("SELECT * FROM repositories WHERE root_path=?", (root_path,)).fetchone())

    def create_repository(self, repository_id: str, name: str, root_path: str) -> dict[str, Any]:
        with self.connect() as db:
            db.execute(
                "INSERT INTO repositories(id,name,root_path) VALUES(?,?,?)",
                (repository_id, name, root_path),
            )
        return self.get_repository(repository_id) or {}

    def set_status(self, repository_id: str, status: str, error: str | None = None) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE repositories SET status=?, error=? WHERE id=?",
                (status, error, repository_id),
            )

    def replace_index(
        self,
        repository_id: str,
        generation: str,
        files: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        indexed_at: str,
    ) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM chunks_fts WHERE repository_id=?", (repository_id,))
            db.execute("DELETE FROM edges WHERE repository_id=?", (repository_id,))
            db.execute("DELETE FROM chunks WHERE repository_id=?", (repository_id,))
            db.execute("DELETE FROM files WHERE repository_id=?", (repository_id,))
            db.executemany(
                "INSERT INTO files(repository_id,path,sha256,content,language) VALUES(?,?,?,?,?)",
                [(repository_id, f["path"], f["sha256"], f["content"], f["language"]) for f in files],
            )
            db.executemany(
                """INSERT INTO chunks(
                   id,repository_id,file_path,language,object_type,object_name,address,
                   start_line,end_line,content,embedding_text,metadata_json,generation
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(
                    c["id"], repository_id, c["file_path"], c["language"], c["object_type"],
                    c.get("object_name"), c.get("address"), c["start_line"], c["end_line"],
                    c["content"], c["embedding_text"], json.dumps(c.get("metadata", {})), generation,
                ) for c in chunks],
            )
            db.executemany(
                "INSERT INTO chunks_fts(chunk_id,repository_id,file_path,address,object_name,content) VALUES(?,?,?,?,?,?)",
                [(c["id"], repository_id, c["file_path"], c.get("address") or "", c.get("object_name") or "", c["content"]) for c in chunks],
            )
            db.executemany(
                "INSERT INTO edges(repository_id,source_chunk_id,relationship,target,target_chunk_id,metadata_json) VALUES(?,?,?,?,?,?)",
                [(repository_id, e["source_chunk_id"], e["relationship"], e["target"], e.get("target_chunk_id"), json.dumps(e.get("metadata", {}))) for e in edges],
            )
            db.execute(
                """UPDATE repositories SET status='ready', generation=?, file_count=?, chunk_count=?,
                   edge_count=?, indexed_at=?, error=NULL WHERE id=?""",
                (generation, len(files), len(chunks), len(edges), indexed_at, repository_id),
            )

    def files(self, repository_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT path,language,length(content) AS bytes FROM files WHERE repository_id=? ORDER BY path",
                (repository_id,),
            )]

    def source(self, repository_id: str, path: str) -> dict[str, Any] | None:
        with self.connect() as db:
            return self.row(db.execute(
                "SELECT path,language,content FROM files WHERE repository_id=? AND path=?",
                (repository_id, path),
            ).fetchone())

    def chunk(self, chunk_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = self.row(db.execute("SELECT * FROM chunks WHERE id=?", (chunk_id,)).fetchone())
        if row:
            row["metadata"] = json.loads(row.pop("metadata_json"))
        return row

    def chunks(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        marks = ",".join("?" for _ in ids)
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(f"SELECT * FROM chunks WHERE id IN ({marks})", ids)]
        indexed = {row["id"]: row for row in rows}
        for row in rows:
            row["metadata"] = json.loads(row.pop("metadata_json"))
        return [indexed[item] for item in ids if item in indexed]

    def lexical_search(self, repository_id: str, query: str, limit: int) -> list[tuple[str, float]]:
        tokens = [token.replace('"', "") for token in query.split() if token.strip()]
        if not tokens:
            return []
        expression = " OR ".join(f'"{token}"' for token in tokens[:12])
        with self.connect() as db:
            try:
                rows = db.execute(
                    "SELECT chunk_id,bm25(chunks_fts) AS rank FROM chunks_fts WHERE chunks_fts MATCH ? AND repository_id=? ORDER BY rank LIMIT ?",
                    (expression, repository_id, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        return [(row["chunk_id"], float(-row["rank"])) for row in rows]

    def exact_search(self, repository_id: str, query: str, limit: int) -> list[tuple[str, float]]:
        needle = f"%{query.lower()}%"
        with self.connect() as db:
            rows = db.execute(
                """SELECT id,address,file_path,object_name FROM chunks WHERE repository_id=? AND
                   (lower(address) LIKE ? OR lower(file_path) LIKE ? OR lower(object_name) LIKE ?)
                   ORDER BY CASE WHEN lower(address)=lower(?) THEN 0 ELSE 1 END, length(file_path) LIMIT ?""",
                (repository_id, needle, needle, needle, query, limit),
            ).fetchall()
        return [(row["id"], 1.0) for row in rows]

    def graph(self, repository_id: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                """SELECT e.id,e.relationship,e.target,e.source_chunk_id,e.target_chunk_id,
                   c.file_path AS source_file,c.address AS source_address
                   FROM edges e JOIN chunks c ON c.id=e.source_chunk_id
                   WHERE e.repository_id=? ORDER BY source_file,relationship,target""",
                (repository_id,),
            )]

    def related_chunks(self, repository_id: str, chunk_ids: list[str], limit: int = 20) -> list[str]:
        if not chunk_ids:
            return []
        marks = ",".join("?" for _ in chunk_ids)
        params: list[Any] = [repository_id, *chunk_ids, *chunk_ids, limit]
        with self.connect() as db:
            rows = db.execute(
                f"""SELECT DISTINCT COALESCE(target_chunk_id, source_chunk_id) AS id FROM edges
                    WHERE repository_id=? AND (source_chunk_id IN ({marks}) OR target_chunk_id IN ({marks}))
                    AND COALESCE(target_chunk_id, source_chunk_id) IS NOT NULL LIMIT ?""",
                params,
            ).fetchall()
        return [row["id"] for row in rows]

    def cached_embeddings(self, chunks: list[dict[str, Any]], model: str) -> dict[str, list[float]]:
        if not chunks:
            return {}
        ids = [chunk["id"] for chunk in chunks]
        marks = ",".join("?" for _ in ids)
        with self.connect() as db:
            rows = db.execute(
                f"SELECT chunk_id,content_sha256,vector_json FROM embedding_cache WHERE model=? AND chunk_id IN ({marks})",
                [model, *ids],
            ).fetchall()
        expected = {
            chunk["id"]: hashlib.sha256(chunk["embedding_text"].encode()).hexdigest()
            for chunk in chunks
        }
        return {
            row["chunk_id"]: json.loads(row["vector_json"])
            for row in rows if expected.get(row["chunk_id"]) == row["content_sha256"]
        }

    def cache_embeddings(self, chunks: list[dict[str, Any]], model: str, vectors: list[list[float]]) -> None:
        with self.connect() as db:
            db.executemany(
                """INSERT INTO embedding_cache(chunk_id,model,content_sha256,vector_json) VALUES(?,?,?,?)
                   ON CONFLICT(chunk_id,model) DO UPDATE SET content_sha256=excluded.content_sha256,vector_json=excluded.vector_json""",
                [(
                    chunk["id"], model, hashlib.sha256(chunk["embedding_text"].encode()).hexdigest(), json.dumps(vector)
                ) for chunk, vector in zip(chunks, vectors, strict=True)],
            )

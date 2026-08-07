import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

import pathspec
import tree_sitter_hcl
from tree_sitter import Language, Node, Parser


INCLUDED_SUFFIXES = {".tf", ".tfvars", ".hcl", ".md", ".mdx", ".yaml", ".yml", ".json"}
EXCLUDED_DIRS = {".git", ".terraform", "node_modules", "vendor", ".venv", ".next", "__pycache__"}
EXCLUDED_NAMES = {".env", ".env.local", ".env.production"}
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".tfstate", ".tfstate.backup"}
SECRET_NAME_RE = re.compile(r"(?i)(credential|secret|private[_-]?key|service[_-]?account)")
SYMBOL_RE = re.compile(r"\b(?:var|local|module|data|dependency|[A-Za-z_][\w-]*)\.[A-Za-z0-9_.-]+")
DEPENDENCY_OUTPUT_RE = re.compile(r"\bdependency\.([\w-]+)\.outputs\.([\w-]+)")
STRING_RE = re.compile(r'"([^"\n]+)"')
SOURCE_RE = re.compile(r"(?m)^\s*source\s*=\s*\"([^\"]+)\"")
CONFIG_PATH_RE = re.compile(r"(?m)^\s*config_path\s*=\s*\"([^\"]+)\"")
PARENT_FILE_RE = re.compile(r"find_in_parent_folders\(\s*\"([^\"]+)\"")
MARKDOWN_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*$")


class UnsafeRepository(ValueError):
    pass


def resolve_repository(repository_root: Path, requested: str) -> Path:
    root = repository_root.resolve()
    candidate = Path(requested)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve(strict=True)
    if not candidate.is_dir() or (candidate != root and root not in candidate.parents):
        raise UnsafeRepository("Repository path must be a directory below the configured repository root")
    return candidate


def _ignored(relative: str, path: Path, ignore: pathspec.PathSpec | None) -> bool:
    parts = Path(relative).parts
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    if path.name in EXCLUDED_NAMES or path.name.startswith(".env.") or path.name.endswith((".tfstate", ".tfstate.backup")):
        return True
    if path.suffix.lower() in SECRET_SUFFIXES or SECRET_NAME_RE.search(path.name):
        return True
    return bool(ignore and ignore.match_file(relative))


def scan_repository(root: Path) -> list[dict[str, Any]]:
    ignore_file = root / ".terraragignore"
    ignore = pathspec.PathSpec.from_lines("gitwildmatch", ignore_file.read_text().splitlines()) if ignore_file.is_file() else None
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if _ignored(relative, path, ignore) or path.suffix.lower() not in INCLUDED_SUFFIXES:
            continue
        resolved = path.resolve()
        if root != resolved and root not in resolved.parents:
            continue
        try:
            raw = path.read_bytes()
            if len(raw) > 2_000_000 or b"\x00" in raw:
                continue
            content = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        language = (
            "terragrunt" if path.name.endswith(".hcl")
            else "terraform" if path.suffix in {".tf", ".tfvars"}
            else "markdown" if path.suffix.lower() in {".md", ".mdx"}
            else "text"
        )
        files.append({
            "path": relative,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "content": content,
            "language": language,
        })
    return files


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")


def _labels(node: Node, source: bytes) -> tuple[str, list[str]]:
    named = [child for child in node.named_children if child.type in {"identifier", "string_lit"}]
    block_type = _node_text(named[0], source).strip('"') if named else "block"
    labels = [_node_text(child, source).strip('"') for child in named[1:]]
    return block_type, labels


def _address(block_type: str, labels: list[str]) -> str | None:
    if block_type in {"resource", "data"} and len(labels) >= 2:
        return f"{block_type + '.' if block_type == 'data' else ''}{labels[0]}.{labels[1]}"
    if block_type == "module" and labels:
        return f"module.{labels[0]}"
    if block_type == "variable" and labels:
        return f"var.{labels[0]}"
    if block_type == "output" and labels:
        return f"output.{labels[0]}"
    if labels:
        return f"{block_type}.{'.'.join(labels)}"
    return block_type


def _environment(file_path: str) -> str | None:
    parts = Path(file_path).parts
    for marker in ("live", "environments", "envs"):
        if marker in parts:
            index = parts.index(marker)
            return parts[index + 1] if len(parts) > index + 1 else None
    return None


def _chunk(file: dict[str, Any], node: Node, object_type: str, name: str | None, address: str | None) -> dict[str, Any]:
    source = file["content"].encode("utf-8")
    content = _node_text(node, source)
    start_line = node.start_point.row + 1
    end_line = node.end_point.row + 1
    symbols = sorted(set(SYMBOL_RE.findall(content)))
    metadata = {
        "symbols_referenced": symbols,
        "environment": _environment(file["path"]),
        "parse_error": node.has_error,
    }
    identity = f'{file["path"]}:{start_line}:{end_line}:{object_type}:{address or name or ""}'
    chunk_id = str(uuid.uuid5(uuid.NAMESPACE_URL, identity))
    context = f"file: {file['path']}\nlanguage: {file['language']}\nobject: {object_type} {address or name or ''}\n"
    return {
        "id": chunk_id,
        "file_path": file["path"],
        "language": file["language"],
        "object_type": object_type,
        "object_name": name,
        "address": address,
        "start_line": start_line,
        "end_line": end_line,
        "content": content,
        "embedding_text": context + content,
        "metadata": metadata,
    }


def _document_provenance(file_path: str) -> dict[str, Any]:
    parts = Path(file_path).parts
    if len(parts) >= 2 and parts[0] == "terraform":
        return {"corpus": "official_docs", "product": "Terraform", "version": parts[1]}
    if len(parts) >= 2 and parts[0] == "terragrunt":
        return {"corpus": "official_docs", "product": "Terragrunt", "version": parts[1]}
    return {"corpus": "repository", "product": None, "version": None}


def _document_chunks(file: dict[str, Any]) -> list[dict[str, Any]]:
    lines = file["content"].splitlines()
    if not lines:
        lines = [""]
    headings: list[int] = []
    fence: str | None = None
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        marker = "```" if stripped.startswith("```") else "~~~" if stripped.startswith("~~~") else None
        if marker:
            fence = None if fence == marker else marker if fence is None else fence
            continue
        if fence is None and MARKDOWN_HEADING_RE.match(line):
            headings.append(index)
    boundaries = sorted(set([0, *headings, len(lines)]))
    sections: list[tuple[int, int]] = []
    for index, start in enumerate(boundaries[:-1]):
        end = boundaries[index + 1]
        if end > start:
            sections.append((start, end))

    chunks: list[dict[str, Any]] = []
    provenance = _document_provenance(file["path"])
    for section_start, section_end in sections:
        heading_match = MARKDOWN_HEADING_RE.match(lines[section_start])
        heading = heading_match.group(2).strip() if heading_match else Path(file["path"]).name
        heading = re.sub(r"[`*_{}<>]", "", heading)[:180]
        start = section_start
        while start < section_end:
            end = min(section_end, start + 80)
            while end > start + 1 and len("\n".join(lines[start:end])) > 4_800:
                end -= 1
            content = "\n".join(lines[start:end])
            if not content.strip():
                start = end
                continue
            identity = f'{file["path"]}:{start + 1}:{end}:document:{heading}'
            address = f'doc:{file["path"]}#{re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")}'
            metadata = {
                "symbols_referenced": [], "environment": None, "parse_error": False,
                "heading": heading, **provenance,
            }
            context = (
                f"corpus: {provenance['corpus']}\nproduct: {provenance.get('product') or 'repository'}\n"
                f"version: {provenance.get('version') or 'unversioned'}\nfile: {file['path']}\nsection: {heading}\n"
            )
            chunks.append({
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, identity)),
                "file_path": file["path"], "language": file["language"], "object_type": "document",
                "object_name": heading, "address": address,
                "start_line": start + 1, "end_line": end,
                "content": content, "embedding_text": context + content[:4_800],
                "metadata": metadata,
            })
            start = end
    return chunks


def parse_file(file: dict[str, Any]) -> list[dict[str, Any]]:
    if file["language"] in {"text", "markdown"}:
        return _document_chunks(file)

    source = file["content"].encode("utf-8")
    parser = Parser(Language(tree_sitter_hcl.language()))
    tree = parser.parse(source)
    body = next((child for child in tree.root_node.named_children if child.type == "body"), tree.root_node)
    chunks: list[dict[str, Any]] = []
    for node in body.named_children:
        if node.type == "block":
            block_type, labels = _labels(node, source)
            name = ".".join(labels) if labels else block_type
            chunks.append(_chunk(file, node, block_type, name, _address(block_type, labels)))
        elif node.type == "attribute":
            identifier = next((child for child in node.named_children if child.type == "identifier"), None)
            name = _node_text(identifier, source) if identifier else "attribute"
            chunks.append(_chunk(file, node, name, name, name))
    if not chunks and file["content"].strip():
        chunks.append(_chunk(file, tree.root_node, "file", Path(file["path"]).name, file["path"]))
    return chunks


def build_edges(chunks: list[dict[str, Any]], repository_root: Path) -> list[dict[str, Any]]:
    by_address = {chunk.get("address"): chunk["id"] for chunk in chunks if chunk.get("address")}
    by_file = {chunk["file_path"]: chunk["id"] for chunk in chunks}
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add(source: str, relationship: str, target: str, target_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        key = (source, relationship, target)
        if key not in seen:
            seen.add(key)
            edges.append({"source_chunk_id": source, "relationship": relationship, "target": target, "target_chunk_id": target_id, "metadata": metadata or {}})

    for chunk in chunks:
        content = chunk["content"]
        for symbol in chunk["metadata"]["symbols_referenced"]:
            target_id = by_address.get(symbol)
            if target_id and target_id != chunk["id"]:
                add(chunk["id"], "references", symbol, target_id)
        for dependency, output in DEPENDENCY_OUTPUT_RE.findall(content):
            target = f"dependency.{dependency}"
            add(chunk["id"], "feeds_from", f"{target}.outputs.{output}", by_address.get(target), {"output": output})
        if chunk["object_type"] == "dependency":
            match = CONFIG_PATH_RE.search(content)
            if match:
                absolute_target = (repository_root / Path(chunk["file_path"]).parent / match.group(1) / "terragrunt.hcl").resolve()
                try:
                    target_path = absolute_target.relative_to(repository_root).as_posix()
                except ValueError:
                    target_path = absolute_target.as_posix()
                add(chunk["id"], "dependency", target_path, by_file.get(target_path), {"config_path": match.group(1)})
        if chunk["object_type"] == "terraform":
            match = SOURCE_RE.search(content)
            if match:
                add(chunk["id"], "terraform_source", match.group(1))
        if chunk["object_type"] == "include":
            parent = PARENT_FILE_RE.search(content)
            if parent:
                current = (repository_root / chunk["file_path"]).parent
                target_path = None
                while repository_root in (current, *current.parents):
                    candidate = current / parent.group(1)
                    if candidate.is_file():
                        target_path = candidate.relative_to(repository_root).as_posix()
                        break
                    if current == repository_root:
                        break
                    current = current.parent
                add(chunk["id"], "includes", target_path or parent.group(1), by_file.get(target_path or ""), {"unresolved": target_path is None})
    return edges


def parse_repository(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    files = scan_repository(root)
    chunks = [chunk for file in files for chunk in parse_file(file)]
    edges = build_edges(chunks, root)
    return files, chunks, edges

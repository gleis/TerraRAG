from pathlib import Path

from app.ingestion import parse_repository, resolve_repository


EXAMPLE = Path(__file__).parents[2] / "example-infra"


def test_parser_preserves_lines_and_addresses() -> None:
    files, chunks, edges = parse_repository(EXAMPLE)
    worker = next(item for item in chunks if item["address"] == "aws_instance.worker")

    assert worker["file_path"] == "modules/app/main.tf"
    assert worker["start_line"] == 21
    assert worker["end_line"] == 31
    assert "var.instance_type" in worker["metadata"]["symbols_referenced"]
    assert files and edges


def test_terragrunt_dependency_and_secret_exclusion() -> None:
    files, chunks, edges = parse_repository(EXAMPLE)
    paths = {item["path"] for item in files}
    dependency = next(
        item for item in chunks
        if item["file_path"] == "live/prod/us-east-1/app/terragrunt.hcl" and item["object_type"] == "dependency"
    )

    assert "ignored/credentials.json" not in paths
    assert any(
        edge["source_chunk_id"] == dependency["id"]
        and edge["relationship"] == "dependency"
        and edge["target"] == "live/prod/us-east-1/network/terragrunt.hcl"
        and edge["target_chunk_id"]
        for edge in edges
    )
    assert any(edge["relationship"] == "feeds_from" and edge["metadata"].get("output") == "vpc_id" for edge in edges)


def test_repository_path_cannot_escape(tmp_path: Path) -> None:
    root = tmp_path / "repos"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    try:
        resolve_repository(root, str(outside))
    except ValueError as exc:
        assert "below" in str(exc)
    else:
        raise AssertionError("outside path should be rejected")


def test_markdown_is_chunked_by_heading_with_provenance(tmp_path: Path) -> None:
    root = tmp_path / "reference-docs"
    page = root / "terraform" / "v1.15.x" / "language" / "resources.mdx"
    page.parent.mkdir(parents=True)
    page.write_text("# Resources\nOverview.\n\n## Lifecycle\nUse lifecycle settings.\n")

    files, chunks, edges = parse_repository(root)

    assert files[0]["language"] == "markdown"
    assert [chunk["object_name"] for chunk in chunks] == ["Resources", "Lifecycle"]
    assert chunks[1]["start_line"] == 4
    assert chunks[1]["metadata"] == {
        "symbols_referenced": [], "environment": None, "parse_error": False,
        "heading": "Lifecycle", "corpus": "official_docs", "product": "Terraform", "version": "v1.15.x",
    }
    assert not edges


def test_markdown_ignores_headings_inside_fenced_code(tmp_path: Path) -> None:
    root = tmp_path / "reference-docs"
    page = root / "terragrunt" / "v1.1.2" / "example.mdx"
    page.parent.mkdir(parents=True)
    page.write_text("# Example\n```hcl\n# This is a code comment\nvalue = true\n```\n\n## Real section\nDetails.\n")

    _, chunks, _ = parse_repository(root)

    assert [chunk["object_name"] for chunk in chunks] == ["Example", "Real section"]
    assert "code comment" in chunks[0]["content"]


def test_markdown_embedding_chunks_are_size_bounded(tmp_path: Path) -> None:
    root = tmp_path / "reference-docs"
    page = root / "terraform" / "v1.15.x" / "large.mdx"
    page.parent.mkdir(parents=True)
    page.write_text("# Large section\n" + "\n".join("x" * 240 for _ in range(40)))

    _, chunks, _ = parse_repository(root)

    assert len(chunks) > 1
    assert max(len(chunk["embedding_text"]) for chunk in chunks) < 5_200
    assert "".join(chunk["content"].replace("\n", "") for chunk in chunks).endswith("x" * 240)

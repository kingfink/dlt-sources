"""Generic markdown repository source helpers for dlt pipelines."""

from __future__ import annotations

import importlib
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from itertools import chain
from pathlib import Path
from typing import Any

import yaml

INCREMENTAL_CURSOR_FIELD = "modified_at_cursor"
INCREMENTAL_INITIAL_VALUE = "1970-01-01T00:00:00.000000+00:00|"

RESOURCE_COLUMNS = {
    "file_path": {"data_type": "text"},
    "frontmatter": {"data_type": "json"},
    "content": {"data_type": "text"},
    "created_at": {"data_type": "timestamp"},
    "modified_at": {"data_type": "timestamp"},
    INCREMENTAL_CURSOR_FIELD: {"data_type": "text"},
}


@dataclass(frozen=True)
class MarkdownDocument:
    """Parsed markdown document with YAML frontmatter and body content."""

    frontmatter: dict[str, Any]
    content: str


@dataclass(frozen=True)
class FileTimestamps:
    """Git-derived creation and modification timestamps for one file."""

    created_at: str
    modified_at: str


class GitTimestampResolver:
    """Resolve file timestamps from git history."""

    def __init__(
        self,
        repo_root: Path,
        run_command: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.run_command = run_command

    def __call__(self, file_path: str | Path) -> FileTimestamps:
        relative_path = Path(file_path)
        if relative_path.is_absolute():
            relative_path = relative_path.relative_to(self.repo_root)

        result = self.run_command(
            [
                "git",
                "log",
                "--follow",
                "--format=%aI",
                "--",
                relative_path.as_posix(),
            ],
            cwd=self.repo_root,
            check=True,
            text=True,
            capture_output=True,
        )
        timestamps = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not timestamps:
            raise ValueError(f"No git history found for {relative_path.as_posix()}")

        return FileTimestamps(created_at=timestamps[-1], modified_at=timestamps[0])


def read_markdown_document(path: Path) -> MarkdownDocument:
    """Return parsed frontmatter and body content for a markdown file."""
    return parse_markdown_document(path.read_text(encoding="utf-8"))


def parse_markdown_document(content: str) -> MarkdownDocument:
    """Parse frontmatter and body content from a markdown string."""
    metadata, body = _split_frontmatter(content)
    return MarkdownDocument(frontmatter=metadata or {}, content=body)


def build_resource_rows(
    repo_root: Path = Path("."),
    resource_glob: str | Iterable[str] = "**/*.md",
    *,
    timestamp_resolver: Callable[[Path], FileTimestamps] | None = None,
    exclude_stems: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build rows for markdown files matched by one resource glob."""
    repo_root = Path(repo_root)
    globs = _normalize_globs(resource_glob)
    markdown_files = chain.from_iterable(repo_root.glob(pattern) for pattern in globs)
    return _build_rows(
        repo_root,
        sorted(set(markdown_files)),
        timestamp_resolver,
        exclude_stems=exclude_stems,
    )


def build_file_item_rows(
    file_items,
    timestamp_resolver: Callable[[Path], FileTimestamps],
    *,
    exclude_stems: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build warehouse rows from dlt filesystem FileItems."""
    excluded = exclude_stems or {"index"}
    rows = []
    for file_item in file_items:
        relative_path = Path(str(file_item["relative_path"]))
        if relative_path.stem in excluded:
            continue
        rows.append(
            build_markdown_row(
                relative_path,
                _read_file_item(file_item),
                timestamp_resolver,
            )
        )
    return rows


def build_markdown_row(
    relative_path: Path,
    markdown_content: str,
    timestamp_resolver: Callable[[Path], FileTimestamps],
) -> dict[str, Any]:
    """Build one warehouse row from markdown content and git timestamps."""
    document = parse_markdown_document(markdown_content)
    timestamps = timestamp_resolver(relative_path)
    return {
        "file_path": relative_path.as_posix(),
        "frontmatter": _json_safe(document.frontmatter),
        "content": document.content,
        "created_at": timestamps.created_at,
        "modified_at": timestamps.modified_at,
        "modified_at_cursor": _modified_at_cursor(timestamps.modified_at, relative_path),
    }


def build_dlt_resources(
    dlt_module,
    *,
    repo_root: Path,
    resource_globs: dict[str, str | Iterable[str]],
    filesystem_resource=None,
    timestamp_resolver=None,
    exclude_stems: set[str] | None = None,
):
    """Return dlt resources for every configured markdown resource glob."""
    if not resource_globs:
        raise ValueError("resource_globs must include at least one resource")

    repo_root = Path(repo_root).resolve()
    resolver = timestamp_resolver or GitTimestampResolver(repo_root)
    filesystem = filesystem_resource or _filesystem_resource()
    return [
        _incremental_resource(
            dlt_module,
            resource_name,
            _file_items_for_globs(filesystem, repo_root, globs),
            resolver,
            exclude_stems=exclude_stems,
        )
        for resource_name, globs in resource_globs.items()
    ]


def git_repo_markdown_files_source(
    *,
    repo_root: Path = Path("."),
    resource_globs: dict[str, str | Iterable[str]],
    timestamp_resolver=None,
    exclude_stems: set[str] | None = None,
):
    """Build a list of dlt resources for markdown files in a repository."""
    dlt_module = importlib.import_module("dlt")
    return build_dlt_resources(
        dlt_module,
        repo_root=repo_root,
        resource_globs=resource_globs,
        timestamp_resolver=timestamp_resolver,
        exclude_stems=exclude_stems,
    )


def _build_rows(
    repo_root: Path,
    markdown_files,
    timestamp_resolver: Callable[[Path], FileTimestamps] | None,
    *,
    exclude_stems: set[str] | None,
) -> list[dict[str, Any]]:
    resolver = timestamp_resolver or GitTimestampResolver(repo_root)
    excluded = exclude_stems or {"index"}
    rows = []
    for file_path in markdown_files:
        if file_path.stem in excluded:
            continue
        relative_path = file_path.relative_to(repo_root)
        rows.append(
            build_markdown_row(relative_path, file_path.read_text(encoding="utf-8"), resolver)
        )
    return rows


def _incremental_resource(
    dlt_module,
    table_name: str,
    file_items,
    timestamp_resolver,
    *,
    exclude_stems: set[str] | None,
):
    @dlt_module.resource(
        name=table_name,
        primary_key="file_path",
        write_disposition="merge",
        columns=RESOURCE_COLUMNS,
    )
    def markdown_rows(
        modified_at=dlt_module.sources.incremental(  # noqa: B008
            INCREMENTAL_CURSOR_FIELD,
            initial_value=INCREMENTAL_INITIAL_VALUE,
            row_order="asc",
        ),
    ):
        del modified_at
        ordered_rows = sorted(
            build_file_item_rows(
                file_items,
                timestamp_resolver,
                exclude_stems=exclude_stems,
            ),
            key=lambda row: str(row[INCREMENTAL_CURSOR_FIELD]),
        )
        yield from ordered_rows

    return markdown_rows


def _file_items_for_globs(filesystem_resource, repo_root: Path, globs: str | Iterable[str]):
    return list(
        chain.from_iterable(
            filesystem_resource(
                bucket_url=repo_root.as_uri(),
                file_glob=glob_pattern,
            )
            for glob_pattern in _normalize_globs(globs)
        )
    )


def _normalize_globs(globs: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(globs, str):
        return (globs,)
    return tuple(globs)


def _filesystem_resource():
    return importlib.import_module("dlt.sources.filesystem").filesystem


def _split_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    """Split markdown into parsed frontmatter and body."""
    if not content.startswith("---"):
        return None, content

    end = content.find("---", 3)
    if end == -1:
        return None, content

    raw_block = content[3:end].strip("\n")
    body = content[end + 3 :]

    try:
        metadata = yaml.safe_load(raw_block)
    except yaml.YAMLError:
        return None, body

    if not isinstance(metadata, dict):
        return None, body

    return metadata, body


def _read_file_item(file_item) -> str:
    with file_item.open() as file:
        content = file.read()
    if isinstance(content, bytes):
        return content.decode("utf-8")
    return str(content)


def _json_safe(value):
    """Convert PyYAML scalar types into values suitable for a JSON column."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _modified_at_cursor(modified_at: str, relative_path: Path) -> str:
    timestamp = modified_at.replace("Z", "+00:00")
    modified_datetime = datetime.fromisoformat(timestamp)
    if modified_datetime.tzinfo is None:
        modified_datetime = modified_datetime.replace(tzinfo=UTC)
    normalized_timestamp = modified_datetime.astimezone(UTC).isoformat(timespec="microseconds")
    return f"{normalized_timestamp}|{relative_path.as_posix()}"

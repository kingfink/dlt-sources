from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from tailor_made_dlt_sources.git_repo_markdown_files import (
    FileTimestamps,
    GitTimestampResolver,
    build_dlt_resources,
    build_file_item_rows,
    build_markdown_row,
    build_resource_rows,
    git_repo_markdown_files_source,
    read_markdown_document,
)


def test_read_markdown_document_returns_frontmatter_and_body(tmp_path: Path) -> None:
    path = tmp_path / "post.md"
    path.write_text(
        "---\ntitle: Analytics Engineer\ndate: 2026-04-22\ntags:\n  - SQL\n---\nBody\n",
        encoding="utf-8",
    )

    document = read_markdown_document(path)

    assert document.frontmatter == {
        "title": "Analytics Engineer",
        "date": date(2026, 4, 22),
        "tags": ["SQL"],
    }
    assert document.content == "\nBody\n"


def test_git_timestamp_resolver_uses_oldest_and_newest_history_entries(tmp_path: Path) -> None:
    calls = []

    def fake_run(args, cwd, check, text, capture_output):
        calls.append(
            {
                "args": args,
                "cwd": cwd,
                "check": check,
                "text": text,
                "capture_output": capture_output,
            }
        )
        return SimpleNamespace(stdout="2026-04-22T23:23:35-04:00\n2025-11-01T08:15:00-04:00\n")

    resolver = GitTimestampResolver(tmp_path, run_command=fake_run)

    timestamps = resolver("content/posts/example.md")

    assert timestamps == FileTimestamps(
        created_at="2025-11-01T08:15:00-04:00",
        modified_at="2026-04-22T23:23:35-04:00",
    )
    assert calls == [
        {
            "args": [
                "git",
                "log",
                "--follow",
                "--format=%aI",
                "--",
                "content/posts/example.md",
            ],
            "cwd": tmp_path,
            "check": True,
            "text": True,
            "capture_output": True,
        }
    ]


def test_build_resource_rows_uses_resource_glob_and_excludes_index(tmp_path: Path) -> None:
    _write_markdown(tmp_path / "docs/jobs/acme/z-last.md", "---\ntitle: Last\n---\nLast\n")
    _write_markdown(tmp_path / "docs/jobs/acme/a-first.md", "---\ntitle: First\n---\nFirst\n")
    _write_markdown(tmp_path / "docs/jobs/index.md", "---\ntitle: Index\n---\n")

    rows = build_resource_rows(
        tmp_path,
        "docs/jobs/**/*.md",
        timestamp_resolver=lambda path: FileTimestamps(
            created_at=f"created:{path.as_posix()}",
            modified_at="2026-01-01T00:00:00+00:00",
        ),
    )

    assert [row["file_path"] for row in rows] == [
        "docs/jobs/acme/a-first.md",
        "docs/jobs/acme/z-last.md",
    ]
    assert rows[0]["frontmatter"] == {"title": "First"}
    assert rows[0]["content"] == "\nFirst\n"


def test_build_markdown_row_adds_unique_incremental_cursor() -> None:
    row = build_markdown_row(
        Path("docs/jobs/acme/analytics-engineer.md"),
        "---\ntitle: Analytics Engineer\n---\nJob body\n",
        timestamp_resolver=lambda path: FileTimestamps(
            created_at="2025-01-01T00:00:00+00:00",
            modified_at="2026-01-01T03:04:05-05:00",
        ),
    )

    assert row["modified_at"] == "2026-01-01T03:04:05-05:00"
    assert (
        row["modified_at_cursor"]
        == "2026-01-01T08:04:05.000000+00:00|docs/jobs/acme/analytics-engineer.md"
    )


def test_build_dlt_resources_configures_each_resource_glob() -> None:
    dlt = FakeDlt()
    filesystem = FakeFilesystem(
        {
            "docs/jobs/**/*.md": [
                FakeFileItem("docs/jobs/acme/job.md", "---\ntitle: Job\n---\nJob\n"),
                FakeFileItem("docs/jobs/index.md", "---\ntitle: Index\n---\n"),
            ],
            "docs/organizations/*.md": [
                FakeFileItem("docs/organizations/acme.md", "---\ntitle: Acme\n---\nOrg\n")
            ],
        }
    )

    resources = build_dlt_resources(
        dlt,
        repo_root=Path("/repo"),
        resource_globs={
            "jobs": "docs/jobs/**/*.md",
            "organizations": "docs/organizations/*.md",
        },
        filesystem_resource=filesystem,
        timestamp_resolver=lambda path: FileTimestamps(
            created_at=f"created:{path.as_posix()}",
            modified_at="2026-01-01T00:00:00+00:00",
        ),
    )

    assert filesystem.calls == [
        {"bucket_url": Path("/repo").as_uri(), "file_glob": "docs/jobs/**/*.md"},
        {"bucket_url": Path("/repo").as_uri(), "file_glob": "docs/organizations/*.md"},
    ]
    assert [call["name"] for call in dlt.resource_calls] == ["jobs", "organizations"]
    assert [resource.name for resource in resources] == ["jobs", "organizations"]
    assert list(resources[0]()) == [
        {
            "file_path": "docs/jobs/acme/job.md",
            "frontmatter": {"title": "Job"},
            "content": "\nJob\n",
            "created_at": "created:docs/jobs/acme/job.md",
            "modified_at": "2026-01-01T00:00:00+00:00",
            "modified_at_cursor": "2026-01-01T00:00:00.000000+00:00|docs/jobs/acme/job.md",
        }
    ]


def test_build_file_item_rows_accepts_bytes_and_skips_configured_stems() -> None:
    rows = build_file_item_rows(
        [
            FakeFileItem("content/index.md", b"---\ntitle: Index\n---\n"),
            FakeFileItem("content/post.md", b"---\ntitle: Post\n---\nBody\n"),
        ],
        timestamp_resolver=lambda path: FileTimestamps(
            created_at="2026-01-01T00:00:00+00:00",
            modified_at="2026-01-02T00:00:00+00:00",
        ),
        exclude_stems={"index"},
    )

    assert [row["file_path"] for row in rows] == ["content/post.md"]


def test_build_dlt_resources_rejects_empty_resource_globs() -> None:
    with pytest.raises(ValueError, match="resource_globs"):
        build_dlt_resources(FakeDlt(), repo_root=Path("/repo"), resource_globs={})


def test_source_function_uses_git_repo_markdown_files_name() -> None:
    assert git_repo_markdown_files_source.__name__ == "git_repo_markdown_files_source"


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class FakeFileItem:
    def __init__(self, relative_path: str, content: str | bytes) -> None:
        self.relative_path = relative_path
        self.content = content

    def __getitem__(self, key: str):
        if key == "relative_path":
            return self.relative_path
        raise KeyError(key)

    def open(self):
        return FakeOpen(self.content)


class FakeOpen:
    def __init__(self, content: str | bytes) -> None:
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self):
        return self.content


class FakeFilesystem:
    def __init__(self, files_by_glob):
        self.files_by_glob = files_by_glob
        self.calls = []

    def __call__(self, *, bucket_url, file_glob):
        self.calls.append({"bucket_url": bucket_url, "file_glob": file_glob})
        return self.files_by_glob[file_glob]


class FakeDlt:
    def __init__(self) -> None:
        self.resource_calls = []
        self.sources = SimpleNamespace(incremental=FakeIncremental)

    def resource(self, **kwargs):
        self.resource_calls.append(kwargs)

        def decorator(func):
            return FakeResource(kwargs["name"], func)

        return decorator


class FakeResource:
    def __init__(self, name, func) -> None:
        self.name = name
        self.func = func

    def __call__(self):
        return self.func()


class FakeIncremental:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

"""Runnable demo: load markdown files from this project into DuckDB.

Then:

    python git_repo_markdown_files_pipeline.py
"""

from __future__ import annotations

from pathlib import Path

import dlt

try:
    from git_repo_markdown_files import git_repo_markdown_files_source
except ImportError:
    from tailor_made_dlt_sources.git_repo_markdown_files import git_repo_markdown_files_source


def main() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="git_repo_markdown_files_demo",
        destination="duckdb",
        dataset_name="repo_content",
    )
    info = pipeline.run(
        git_repo_markdown_files_source(
            repo_root=Path("."),
            resource_globs={"markdown_files": "**/*.md"},
        )
    )
    print(info)


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path

from scripts.sync_dlt_init_layout import (
    canonical_source_names,
    expected_sources_files,
    sync,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_canonical_sources_are_self_contained() -> None:
    package_root = REPO_ROOT / "tailor_made_dlt_sources"

    assert canonical_source_names(REPO_ROOT) == [
        "git_repo_markdown_files",
        "netlify_forms",
        "strava",
    ]
    for source_name in canonical_source_names(REPO_ROOT):
        source_root = package_root / source_name
        assert (source_root / "__init__.py").is_file()
        assert (source_root / "README.md").is_file()
        assert (source_root / "requirements.txt").is_file()
        assert (source_root / "pipeline.py").is_file()


def test_sources_tree_matches_generated_dlt_init_layout(tmp_path: Path) -> None:
    repo_root = tmp_path
    package_root = repo_root / "tailor_made_dlt_sources"
    alpha_root = package_root / "alpha"
    alpha_root.mkdir(parents=True)
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (alpha_root / "__init__.py").write_text("from .helpers import value\n", encoding="utf-8")
    (alpha_root / "helpers.py").write_text("value = 1\n", encoding="utf-8")
    (alpha_root / "pipeline.py").write_text(
        "from alpha import value\nprint(value)\n",
        encoding="utf-8",
    )
    (alpha_root / "README.md").write_text("# alpha\n", encoding="utf-8")
    (alpha_root / "requirements.txt").write_text("dlt>=1.5,<2\n", encoding="utf-8")

    written = sync(repo_root)

    assert written == [
        repo_root / "sources" / "alpha",
        repo_root / "sources" / "alpha_pipeline.py",
    ]
    assert expected_sources_files(repo_root) == {
        repo_root / "sources" / "alpha" / "README.md",
        repo_root / "sources" / "alpha" / "__init__.py",
        repo_root / "sources" / "alpha" / "helpers.py",
        repo_root / "sources" / "alpha" / "requirements.txt",
        repo_root / "sources" / "alpha_pipeline.py",
    }
    assert not (repo_root / "sources" / "alpha" / "pipeline.py").exists()
    assert (repo_root / "sources" / "alpha_pipeline.py").read_text(encoding="utf-8") == (
        "from alpha import value\nprint(value)\n"
    )

#!/usr/bin/env python3
"""Generate sources/<name>/ and sources/<name>_pipeline.py for dlt init."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = "tailor_made_dlt_sources"
SOURCES_DIR = "sources"
IGNORED_NAMES = {"__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def canonical_source_names(repo_root: Path = REPO_ROOT) -> list[str]:
    package_root = repo_root / PACKAGE_DIR
    if not package_root.exists():
        return []
    return sorted(
        path.name
        for path in package_root.iterdir()
        if path.is_dir() and not path.name.startswith("_") and (path / "__init__.py").is_file()
    )


def expected_sources_files(repo_root: Path = REPO_ROOT) -> set[Path]:
    return set(expected_sources_content(repo_root))


def expected_sources_content(repo_root: Path = REPO_ROOT) -> dict[Path, bytes]:
    expected: dict[Path, bytes] = {}
    package_root = repo_root / PACKAGE_DIR
    sources_root = repo_root / SOURCES_DIR
    for source_name in canonical_source_names(repo_root):
        source_root = package_root / source_name
        mirror_root = sources_root / source_name
        for path in source_root.rglob("*"):
            if not path.is_file() or _ignored(path) or path.name == "pipeline.py":
                continue
            expected[mirror_root / path.relative_to(source_root)] = path.read_bytes()

        pipeline = source_root / "pipeline.py"
        if pipeline.is_file():
            expected[sources_root / f"{source_name}_pipeline.py"] = pipeline.read_bytes()
    return expected


def sync(repo_root: Path = REPO_ROOT) -> list[Path]:
    package_root = repo_root / PACKAGE_DIR
    sources_root = repo_root / SOURCES_DIR
    sources_root.mkdir(exist_ok=True)

    written: list[Path] = []
    for source_name in canonical_source_names(repo_root):
        source_root = package_root / source_name
        mirror_root = sources_root / source_name
        if mirror_root.exists():
            shutil.rmtree(mirror_root)
        shutil.copytree(source_root, mirror_root, ignore=_copy_ignore)
        written.append(mirror_root)

        pipeline = source_root / "pipeline.py"
        if pipeline.is_file():
            pipeline_target = sources_root / f"{source_name}_pipeline.py"
            shutil.copy2(pipeline, pipeline_target)
            written.append(pipeline_target)

    return written


def check(repo_root: Path = REPO_ROOT) -> int:
    expected = expected_sources_content(repo_root)
    actual_files = _actual_sources_files(repo_root)
    missing = sorted(expected.keys() - actual_files)
    extra = sorted(actual_files - expected.keys())
    changed = sorted(
        path for path in expected.keys() & actual_files if path.read_bytes() != expected[path]
    )

    if not (missing or extra or changed):
        return 0

    print("sources/ is out of sync with tailor_made_dlt_sources/.", file=sys.stderr)
    if missing:
        print("\nMissing:", file=sys.stderr)
        for path in missing:
            print(f"  {path.relative_to(repo_root)}", file=sys.stderr)
    if extra:
        print("\nExtra:", file=sys.stderr)
        for path in extra:
            print(f"  {path.relative_to(repo_root)}", file=sys.stderr)
    if changed:
        print("\nChanged:", file=sys.stderr)
        for path in changed:
            print(f"  {path.relative_to(repo_root)}", file=sys.stderr)
    print("\nRun: uv run python scripts/sync_dlt_init_layout.py", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if sources/ does not match the canonical source folders.",
    )
    args = parser.parse_args(argv)
    if args.check:
        return check(REPO_ROOT)
    for path in sync(REPO_ROOT):
        print(f"synced {path.relative_to(REPO_ROOT)}")
    return 0


def _actual_sources_files(repo_root: Path) -> set[Path]:
    sources_root = repo_root / SOURCES_DIR
    if not sources_root.exists():
        return set()
    return {path for path in sources_root.rglob("*") if path.is_file() and not _ignored(path)}


def _copy_ignore(directory: str, names: list[str]) -> set[str]:
    del directory
    return {
        name
        for name in names
        if name == "pipeline.py" or name in IGNORED_NAMES or Path(name).suffix in IGNORED_SUFFIXES
    }


def _ignored(path: Path) -> bool:
    return any(part in IGNORED_NAMES for part in path.parts) or path.suffix in IGNORED_SUFFIXES


if __name__ == "__main__":
    raise SystemExit(main())

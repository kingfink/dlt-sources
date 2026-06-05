from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_ci_workflows_run_expected_jobs() -> None:
    workflow_dir = REPO_ROOT / ".github" / "workflows"

    ruff = (workflow_dir / "ruff.yml").read_text()
    py_compile = (workflow_dir / "py-compile.yml").read_text()
    tests = (workflow_dir / "tests.yml").read_text()
    dlt_init_layout = (workflow_dir / "dlt-init-layout.yml").read_text()
    build = (workflow_dir / "build.yml").read_text()

    assert "astral-sh/ruff-action@v3" in ruff
    assert "args: check --output-format=github ." in ruff
    assert "git ls-files '*.py' -z | xargs -0 python3 -m py_compile" in py_compile
    assert "uv run --frozen --extra dev pytest -q" in tests
    assert "python3 scripts/sync_dlt_init_layout.py --check" in dlt_init_layout
    assert "uv build" in build


def test_release_workflows_call_release_scripts() -> None:
    workflow_dir = REPO_ROOT / ".github" / "workflows"

    prepare = (workflow_dir / "prepare-release-pr.yml").read_text()
    release = (workflow_dir / "release.yml").read_text()

    assert 'scripts/prepare-release.sh "${{ inputs.tag }}"' in prepare
    assert 'python3 scripts/release_metadata.py verify "${{ inputs.tag }}"' in release
    assert 'scripts/release.sh "${{ inputs.tag }}"' in release
    assert "uv build" in release


def test_prepare_release_stages_all_release_metadata_files() -> None:
    script = (REPO_ROOT / "scripts" / "prepare-release.sh").read_text()

    for metadata_file in [
        "pyproject.toml",
        "uv.lock",
    ]:
        assert metadata_file in script

    assert 'git diff --quiet -- "${release_metadata_files[@]}"' in script
    assert 'git add "${release_metadata_files[@]}"' in script

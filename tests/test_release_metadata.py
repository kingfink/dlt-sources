from __future__ import annotations

import pytest

from scripts import release_metadata


def test_update_and_verify_release_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(release_metadata, "REPO_ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "tailor-made-dlt-sources"',
                'version = "0.1.0"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text(
        "\n".join(
            [
                "[[package]]",
                'name = "tailor-made-dlt-sources"',
                'version = "0.1.0"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    release_metadata.update_release_metadata("v0.2.0")

    assert 'version = "0.2.0"' in (tmp_path / "pyproject.toml").read_text()
    assert 'version = "0.2.0"' in (tmp_path / "uv.lock").read_text()
    release_metadata.verify_release_metadata("v0.2.0")


def test_verify_release_metadata_rejects_mismatched_lock_version(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(release_metadata, "REPO_ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            [
                "[project]",
                'name = "tailor-made-dlt-sources"',
                'version = "0.2.0"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text(
        "\n".join(
            [
                "[[package]]",
                'name = "tailor-made-dlt-sources"',
                'version = "0.1.0"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="uv.lock"):
        release_metadata.verify_release_metadata("v0.2.0")

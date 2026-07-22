# tailor-made-dlt-sources

Reusable [dlt](https://dlthub.com/) sources for data pipelines.

This package is intentionally source-only. Destination configuration, orchestration, Modal functions, and domain-specific models live in downstream pipeline repos.

The layout follows [dlt-hub/verified-sources][verified-sources] ([Paradox-Machines/dlt-sources][paradox-sources]). Canonical source folders live under `tailor_made_dlt_sources/`, and `sources/` is a generated mirror for `dlt init --location`.

[verified-sources]: https://github.com/dlt-hub/verified-sources
[paradox-sources]: https://github.com/Paradox-Machines/dlt-sources

## Sources

| Source | Loads |
|---|---|
| [`git_repo_markdown_files`][git-repo-markdown-files] | Markdown files from repository globs |
| [`netlify_forms`][netlify-forms] | Verified Netlify form submissions |
| [`strava`][strava] | Strava activity summaries and details |

[git-repo-markdown-files]: tailor_made_dlt_sources/git_repo_markdown_files/README.md
[netlify-forms]: tailor_made_dlt_sources/netlify_forms/README.md
[strava]: tailor_made_dlt_sources/strava/README.md

## Install

There are two supported install paths, depending on whether you want a reusable package dependency or a copied `dlt init` starter source.

For package-style usage, install from a GitHub release tag and import from `tailor_made_dlt_sources`. Pinning a tag keeps downstream pipeline runs reproducible.

```bash
uv add "tailor-made-dlt-sources @ git+https://github.com/kingfink/dlt-sources@v0.1.0"
```

```bash
pip install "git+https://github.com/kingfink/dlt-sources@v0.1.0"
```

Replace `v0.1.0` with the release tag you want to pin.

GitHub Releases also attach built wheel and sdist artifacts, so you can install a release artifact directly if you prefer not to install from the git ref.

For scaffold-style usage, use `dlt init --location`. This does not install the package; it copies a standalone source folder, pipeline file, and `requirements.txt` from the generated `sources/` tree into the target project.

```bash
dlt init strava duckdb --location https://github.com/kingfink/dlt-sources
```

## Usage: Git Repo Markdown Files

```python
import dlt

from tailor_made_dlt_sources.git_repo_markdown_files import git_repo_markdown_files_source

pipeline = dlt.pipeline(
    pipeline_name="git_repo_markdown_files_demo",
    destination="duckdb",
    dataset_name="repo_content",
)
pipeline.run(
    git_repo_markdown_files_source(
        repo_root="/path/to/repo",
        resource_globs={
            "documents": "docs/**/*.md",
            "blog_posts": "content/blog/**/*.md",
        },
    )
)
```

## Usage: Netlify Forms

```python
import dlt

from tailor_made_dlt_sources.netlify_forms import netlify_forms_source

pipeline = dlt.pipeline(
    pipeline_name="netlify_forms_demo",
    destination="duckdb",
    dataset_name="netlify",
)
pipeline.run(
    netlify_forms_source(
        access_token="...",
        site_id="...",
    )
)
```

## Usage: Strava

```python
import dlt
from datetime import UTC, datetime

from tailor_made_dlt_sources.strava import strava_source

pipeline = dlt.pipeline(
    pipeline_name="strava_demo",
    destination="duckdb",
    dataset_name="strava",
)
pipeline.run(
    strava_source(
        since=datetime(2024, 1, 1, tzinfo=UTC),
        until=datetime(2024, 2, 1, tzinfo=UTC),
    )
)
```

Configure Strava credentials using dlt secrets:

```toml
[sources.strava]
client_id = "..."
client_secret = "..."
refresh_token = "..."
```

## dlt init

The `sources/` tree is generated for dlt's verified-source scaffolding layout. Edit canonical source code under `tailor_made_dlt_sources/<source>/`, then regenerate the scaffold mirror:

```bash
uv run python scripts/sync_dlt_init_layout.py
```

The CI `dlt init layout` workflow runs `python3 scripts/sync_dlt_init_layout.py --check` so PRs fail if the generated `sources/` mirror drifts from the canonical package.

## Development

```bash
uv sync --extra dev
uv run python scripts/sync_dlt_init_layout.py --check
uv run pytest
uv run ruff check .
```

## Release

Release automation mirrors the CI/release scaffolding used in `2do-tools`. Releases are manual and tag-driven: prepare a version-bump PR, merge it, then publish a GitHub Release for the same tag.

```bash
scripts/prepare-release.sh v0.2.0
scripts/release.sh v0.2.0
```

`scripts/prepare-release.sh` updates `pyproject.toml` and `uv.lock`, verifies the release metadata, runs compile/layout/test/lint/format/build checks, commits the version bump, pushes `codex/release-vX.Y.Z`, and opens a PR.

If the committed metadata already matches the tag, as with the initial `v0.1.0` release, there is no version-bump PR to open. In that case the prepare step runs the same checks and exits successfully; run the `Release` workflow directly with that tag.

After the PR merges, `scripts/release.sh` verifies the merged metadata, runs `uv build`, and creates or updates a GitHub Release with the wheel and sdist from `dist/` attached. The same steps are available as manual GitHub Actions workflows: `Prepare Release PR` and `Release`.

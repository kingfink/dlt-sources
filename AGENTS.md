# Agent instructions

## Scope and tooling

- This repository owns reusable dlt sources. Keep destination configuration, scheduling, Modal orchestration, and domain-specific warehouse models in downstream pipeline repositories.
- Use connector tools first for GitHub discovery, status, logs, metadata, and comments. Use CLI fallbacks when the required action is unavailable through the connector.
- Preserve unrelated worktree changes and keep fixes focused on the affected source.

## Markdown and prose

- Do not hard-wrap Markdown prose or list items. Keep each paragraph or bullet on one physical source line, including in README and agent instruction files.
- Use line breaks for semantic structure: headings, separate paragraphs, lists, tables, block quotes, and code blocks. Leave a blank line before lists and after headings.
- When editing a document with mixed wrapping, make the affected prose consistent with the one-line-per-paragraph convention. The Python line-length setting does not apply to Markdown.
- Use plain, direct language. Document concrete behavior, limitations, and operational steps rather than speculative features.

## Source layout and public interfaces

- Edit source code and source-specific documentation under `tailor_made_dlt_sources/<source>/`. Each source is self-contained, with its own `__init__.py`, `README.md`, `requirements.txt`, and example `pipeline.py`.
- `sources/` is currently a generated mirror for `dlt init --location`. Do not edit it independently. Run `python3 scripts/sync_dlt_init_layout.py` after changing canonical source files, and include the generated changes in the same PR.
- The generator copies each source's `pipeline.py` to `sources/<source>_pipeline.py`; this difference is intentional.
- Preserve both supported consumption paths: package imports under `tailor_made_dlt_sources` and standalone source copies created by `dlt init`. A layout simplification must update generation/publication, packaging, CI, and documented commands together, and verify both paths. Moving the mirror to a publication branch is a proposed follow-up, not the current implementation.
- Keep source schemas, primary keys, write dispositions, cursor behavior, and authentication documented in the canonical source README. Update documentation when those contracts change.

## Extraction and data correctness

- Preserve source values and identifiers. Keep business-specific classification and analytics outside the reusable source.
- Test API pagination and merge/retry behavior where applicable. A successful load is not sufficient evidence that all source records or fields arrived.
- Distinguish event time, source modification time, and actual load time. Use a real ingestion timestamp for freshness; do not relabel event occurrence or Git author time as delivery time.
- Markdown frontmatter delimiters must occupy complete unindented lines. Triple hyphens inside URLs, text, or indented YAML block scalars are field content. Preserve the remaining Markdown body and cover LF and CRLF inputs.
- When investigating missing fields, compare loaded records with the complete original source using an independent check. Repeating the loader's parsing assumption can reproduce its bug and falsely appear to confirm parity.
- Git-backed content uses Git author timestamps and an incremental cursor. A parser fix does not advance those timestamps, so ordinary incremental loading may leave existing rows unrepaired. Document the consumer upgrade and backfill/refresh required, and reconcile the repaired data before reporting recovery.
- Keep source-specific retention and deletion behavior explicit; do not assume merge loading removes records that disappear upstream.

## Validation

- Add focused behavioral regression tests for parser, pagination, state, and schema changes. Include the input that triggered the defect and verify the fields or records that were previously lost.
- After source changes, check the generated layout and run the relevant tests. Run the full suite and build distributions for shared-source, dependency, packaging, or release changes.

```bash
python3 scripts/sync_dlt_init_layout.py --check
uv run --frozen --extra dev pytest -q
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev ruff format --check .
uv build
```

- For documentation-only changes, check the diff and generated mirror when applicable; do not add tests that merely restate instructions or static configuration.
- For changes affecting source discovery or imports, also instantiate the source without making live API calls. For distribution-layout changes, verify package installation and `dlt init` in clean environments.

## Releases and downstream rollout

- Follow the existing release workflow documented in [README.md](README.md#release). `scripts/prepare-release.sh` prepares version metadata and a release PR; `scripts/release.sh` publishes the corresponding release artifacts.
- Keep `pyproject.toml`, the project's entry in `uv.lock`, and the requested release tag consistent. If metadata already matches the requested tag, release preparation runs checks and skips creating an empty version-bump PR.
- Consumers should pin a released version and update their dependency declaration, lockfile, and any version-specific checks together. Keep package release, consumer upgrade/deployment, data reload, and warehouse rebuild distinct in rollout notes.
- A merged parser fix does not repair already loaded data. State which rollout steps actually ran and which remain pending.

"""Runnable demo: load Netlify form submissions into a local DuckDB file.

Configure `.dlt/secrets.toml`:

    [sources.netlify_forms]
    access_token = "..."
    site_id = "..."

Then:

    python netlify_forms_pipeline.py
"""

from __future__ import annotations

import dlt

try:
    from netlify_forms import netlify_forms_source
except ImportError:
    from tailor_made_dlt_sources.netlify_forms import netlify_forms_source


def main() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="netlify_forms_demo",
        destination="duckdb",
        dataset_name="netlify",
    )
    info = pipeline.run(netlify_forms_source())
    print(info)


if __name__ == "__main__":
    main()

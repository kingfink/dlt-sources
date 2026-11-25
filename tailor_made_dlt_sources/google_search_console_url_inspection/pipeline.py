"""Runnable demo: load Search Console URL Inspection results into a local DuckDB file.

Configure `.dlt/secrets.toml`:

    [sources.google_search_console_url_inspection]
    client_id = "..."
    client_secret = "..."
    refresh_token = "..."

Then:

    python google_search_console_url_inspection_pipeline.py
"""

from __future__ import annotations

import dlt

try:
    from google_search_console_url_inspection import google_search_console_url_inspection_source
except ImportError:
    from tailor_made_dlt_sources.google_search_console_url_inspection import (
        google_search_console_url_inspection_source,
    )


def main() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="google_search_console_url_inspection_demo",
        destination="duckdb",
        dataset_name="google_search_console_url_inspection",
    )
    info = pipeline.run(
        google_search_console_url_inspection_source(
            site_url="https://example.com/",
            urls=["https://example.com/", "https://example.com/about"],
        )
    )
    print(info)


if __name__ == "__main__":
    main()

"""Runnable demo: load Strava activities into a local DuckDB file.

Configure `.dlt/secrets.toml`:

    [sources.strava]
    client_id = "..."
    client_secret = "..."
    refresh_token = "..."

Then:

    python strava_pipeline.py
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import dlt

try:
    from strava import strava_source
except ImportError:
    from tailor_made_dlt_sources.strava import strava_source


def main() -> None:
    until = datetime.now(UTC)
    since = until - timedelta(days=30)
    pipeline = dlt.pipeline(
        pipeline_name="strava_demo",
        destination="duckdb",
        dataset_name="strava",
    )
    info = pipeline.run(strava_source(since=since, until=until))
    print(info)


if __name__ == "__main__":
    main()

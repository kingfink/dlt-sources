"""Load Resend broadcast content into a local DuckDB file.

Configure `.dlt/secrets.toml`:

    [sources.resend]
    api_key = "re_..."

Then run the scaffold with `python resend_pipeline.py`.
"""

from __future__ import annotations

import dlt

try:
    from resend import resend_source
except ImportError:
    from tailor_made_dlt_sources.resend import resend_source


def main() -> None:
    pipeline = dlt.pipeline(
        pipeline_name="resend_demo",
        destination="duckdb",
        dataset_name="resend",
    )
    print(pipeline.run(resend_source()))


if __name__ == "__main__":
    main()

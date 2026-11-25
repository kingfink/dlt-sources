# google_search_console_url_inspection

Google Search Console dlt source for the [URL Inspection API](https://developers.google.com/webmaster-tools/v1/urlInspection.index/inspect). Search Console's bulk performance export reports search traffic but not per-URL indexing status; this source calls the URL Inspection endpoint to collect that missing history, one URL at a time.

## Limitation

An inspection reports Google's most recently recorded crawl and index state for a URL. It is not a live test triggered by the call, and the API does not expose historical inspection results. To build history, run this source on a schedule (for example daily) and let the consuming pipeline keep every snapshot; this source does not backfill past days on its own.

## Resources

| Resource | Primary key | Write disposition | Notes |
|---|---|---|---|
| `url_inspections` | `site_url`, `inspection_url`, `snapshot_date` | merge | One row per inspected URL per observation day |

The source accepts the property (`site_url`), an iterable of URLs to inspect, and an optional `snapshot_date` (defaults to the current UTC date). `snapshot_date` is the daily observation key: inspecting the same URL again on the same day merges into the existing row, so retries do not duplicate it, while inspecting on a later day adds a new row and keeps earlier days intact. Selecting which URLs to inspect, scheduling the run, and choosing a destination are left to the consumer.

### Columns

| Column | Source | Notes |
|---|---|---|
| `site_url`, `inspection_url`, `snapshot_date` | request | Merge key |
| `inspected_at` | client | Timestamp this source called the API, not an event or crawl time |
| `raw_response` | response | Full `inspectionResult` payload, preserved as JSON |
| `index_verdict`, `coverage_state`, `robots_txt_state`, `indexing_state`, `page_fetch_state` | `indexStatusResult` | Indexing/crawl status fields |
| `google_canonical`, `user_canonical`, `crawled_as`, `last_crawl_time` | `indexStatusResult` | Canonicalization and crawl details |
| `sitemap`, `referring_urls` | `indexStatusResult` | JSON arrays |
| `rich_results_verdict`, `rich_results_items` | `richResultsResult` | Rich-result findings; `rich_results_items` is the raw JSON array of detected items |
| `amp_result`, `mobile_usability_result` | response | Preserved as JSON when present |

A verdict of `FAIL` or `NEUTRAL` in `index_verdict` or `rich_results_verdict` is a successful inspection reporting Google's indexing opinion, not a request error. Request errors (auth failures, malformed requests, exhausted retries) raise instead of producing a row, so a failed request is never mistaken for an empty or negative result.

## Auth

Configure Google OAuth2 credentials in `.dlt/secrets.toml`. The refresh token must belong to a user with at least read access to the property in Search Console:

```toml
[sources.google_search_console_url_inspection]
client_id = "..."
client_secret = "..."
refresh_token = "..."
```

## Retries and rate limits

Requests retry on transport errors, `401` (token refresh then one retry), `429`, and `5xx`, honoring `Retry-After` when Google sends it. If `429` retries are exhausted, the source stops cleanly, keeps the URLs already inspected, and records the URL it stopped on in the `status` dict passed into the source, so a rerun can resume. Any other unretried HTTP error raises and fails the extraction instead of yielding an empty or partial result silently.

## Example

```python
from datetime import date

import dlt

from tailor_made_dlt_sources.google_search_console_url_inspection import (
    google_search_console_url_inspection_source,
)

pipeline = dlt.pipeline(
    pipeline_name="google_search_console_url_inspection_demo",
    destination="duckdb",
    dataset_name="google_search_console_url_inspection",
)
info = pipeline.run(
    google_search_console_url_inspection_source(
        site_url="https://example.com/",
        urls=["https://example.com/", "https://example.com/about"],
        snapshot_date=date(2024, 1, 1),
    )
)
print(info)
```

# strava

Strava dlt source for activity summaries and detailed activity records.

## Resources

| Resource | Primary key | Write disposition | Notes |
|---|---|---|---|
| `activity_ids` | none | replace | Summary listing, not selected by default |
| `activities` | `id` | merge | Detailed activity records |

The source reads activities over a half-open `[since, until)` time window. Detail
records that have already been seen are skipped once they are older than the
`STRAVA_REFETCH_DAYS` window, which defaults to 7 days.

## Auth

Configure Strava credentials in `.dlt/secrets.toml`:

```toml
[sources.strava]
client_id = "..."
client_secret = "..."
refresh_token = "..."
```

## Example

```python
from datetime import UTC, datetime

import dlt

from tailor_made_dlt_sources.strava import strava_source

pipeline = dlt.pipeline(
    pipeline_name="strava_demo",
    destination="duckdb",
    dataset_name="strava",
)
info = pipeline.run(
    strava_source(
        since=datetime(2024, 1, 1, tzinfo=UTC),
        until=datetime(2024, 2, 1, tzinfo=UTC),
    )
)
print(info)
```

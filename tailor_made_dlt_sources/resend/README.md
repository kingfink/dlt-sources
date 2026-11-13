# resend

Resend broadcast metadata and content from the [list](https://resend.com/docs/api-reference/broadcasts/list-broadcasts) and [detail](https://resend.com/docs/api-reference/broadcasts/get-broadcast) endpoints.

## Resource and schema

| Resource | Primary key | Write disposition | Default selection |
|---|---|---|---|
| `broadcasts` | `broadcast_id` | merge | `status = "sent"` |

API fields pass through, with detail values taking precedence over summaries. `broadcast_id` aliases the original `id`; `loaded_ts` records the UTC fetch time. Additional fields are inferred by dlt, and nested values remain JSON in the same row.

| Column | Type | Meaning |
|---|---|---|
| `broadcast_id`, `id` | text, non-null | Resend broadcast identifier |
| `object`, `name`, `status` | text | Object type, name, and status |
| `audience_id`, `segment_id`, `topic_id` | text | Targeting identifiers |
| `from`, `subject`, `preview_text` | text | Sender, subject, and preview |
| `html`, `text` | text | Original bodies, including whitespace and template placeholders |
| `reply_to` | JSON | Reply addresses |
| `created_at`, `scheduled_at`, `sent_at` | timestamp | Source creation, scheduled send, and send times |
| `loaded_ts` | timestamp, non-null | Extraction time, separate from source event times |

Fields are nullable unless marked otherwise. Bodies are preserved without rendering or generating text. Null and empty bodies are accepted; a detail response missing both body fields fails extraction.

## Pagination, reruns, and retention

Every run follows `limit`/`after` pagination through all available broadcasts and fetches details for each selected broadcast. The first run backfills available content; reruns merge by `broadcast_id`, updating existing rows and adding new ones. There is no persistent cursor: full rescans capture older drafts that become sent and refresh existing content.

Repeated IDs are fetched once per run. Records deleted or no longer selected upstream remain in the destination. Backfills can only recover content still available through the API.

Requests are sequential, with a 30-second timeout. Connection failures, timeouts, HTTP 429, and HTTP 5xx get up to five attempts with exponential backoff or `Retry-After`, capped at 60 seconds. Unrecoverable errors and invalid responses or pagination fail extraction; rerun the load after resolving the failure. Adjust `request_interval` for Resend's shared [rate limits](https://resend.com/docs/api-reference/rate-limit).

## Authentication and options

Configure a [`full_access`](https://resend.com/docs/api-reference/api-keys/create-api-key) API key in `.dlt/secrets.toml`. The source only makes GET requests.

```toml
[sources.resend]
api_key = "re_..."
```

Alternatively set `SOURCES__RESEND__API_KEY` or pass `api_key` explicitly.

| Argument | Default | Behavior |
|---|---|---|
| `sent_only` | `True` | Set to `False` to include all statuses |
| `page_size` | `100` | Summaries per request, from 1 to 100 |
| `request_interval` | `0.5` | Non-negative delay in seconds between calls |

## Usage

After installing a release containing this source:

```python
import dlt

from tailor_made_dlt_sources.resend import resend_source

pipeline = dlt.pipeline(
    pipeline_name="resend_demo",
    destination="duckdb",
    dataset_name="resend",
)
print(pipeline.run(resend_source()))
```

For a standalone copy, replace `RELEASE_TAG` with a release containing this source:

```bash
dlt init resend duckdb --location https://github.com/kingfink/dlt-sources --branch RELEASE_TAG
python resend_pipeline.py
```

Consumers own scheduling, destinations, and warehouse models. Pin the package release and update the lockfile before deployment. Then backfill and verify IDs, counts, and bodies against the API; validate any webhook joins on `broadcast_id`. Releasing the package does not deploy consumers or load data.

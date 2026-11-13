# resend

Reusable dlt source for Resend broadcast metadata, subjects, HTML, and plain text. It uses the [list broadcasts](https://resend.com/docs/api-reference/broadcasts/list-broadcasts) and [retrieve broadcast](https://resend.com/docs/api-reference/broadcasts/get-broadcast) endpoints. It does not load per-recipient emails or engagement events.

## Resource and schema

| Resource | Primary key | Write disposition | Default selection |
|---|---|---|---|
| `resend_broadcasts` | `broadcast_id` | merge | Broadcasts with `status = "sent"` |

The source preserves the API fields from each summary and detail response, with detail values taking precedence. It adds `broadcast_id` as an alias of the original `id` for joins to webhook email records, and `loaded_ts` as the UTC time the detail was fetched. Nested values remain JSON in the same row rather than creating child tables.

| Column | Type | Meaning |
|---|---|---|
| `broadcast_id`, `id` | text, non-null | The unchanged Resend broadcast identifier |
| `object`, `name`, `status` | text | API object type, broadcast name, and current status |
| `audience_id`, `segment_id`, `topic_id` | text | Original targeting identifiers, when supplied by Resend |
| `from`, `subject`, `preview_text` | text | Sender, subject, and preview text |
| `html`, `text` | text | Original broadcast bodies, including whitespace and template placeholders; nullable |
| `reply_to` | JSON | Reply addresses as returned by Resend |
| `created_at` | timestamp | Source creation time |
| `scheduled_at` | timestamp | Source scheduled send time; nullable |
| `sent_at` | timestamp | Source send time; nullable for unsent broadcasts |
| `loaded_ts` | timestamp, non-null | Actual extraction time for this row; distinct from source event times |

Additional API fields pass through and are inferred by dlt. The source does not render templates, strip HTML, generate missing plain text, or classify newsletters. Null or empty bodies remain null or empty; a detail response missing both body fields fails extraction instead of loading a summary as content.

## Pagination, reruns, and retention

Every run lists all available broadcasts using `limit` and `after`, following `has_more` until the end. It fetches the detail endpoint for every selected broadcast. The first run backfills all available matching broadcasts; subsequent runs merge by `broadcast_id`, updating existing content and adding new broadcasts without duplicate rows.

There is no persistent incremental cursor or seen-ID state. A draft created long ago can become sent later, so creation order alone is not a safe incremental boundary. Full rescans also refresh existing content. Repeated IDs within a run are fetched once. Records deleted or no longer selected upstream remain in the destination: merge does not delete absent rows. Only content still available through Resend's API can be backfilled; the source cannot recover deleted or unavailable history.

Requests run sequentially with a default 0.5-second delay between calls and a 30-second request timeout. dlt retries connection failures, timeouts, HTTP 429, and HTTP 5xx up to five total attempts, using exponential backoff and `Retry-After` with a 60-second delay ceiling. Permanent errors, exhausted retries, malformed responses, and non-advancing pagination fail extraction. Failed extraction must be rerun; it is not treated as a successful partial backfill. Resend's [rate limits](https://resend.com/docs/api-reference/rate-limit) are shared across the team's API keys, so adjust `request_interval` for other workloads.

## Authentication and options

Use a Resend API key with [`full_access`](https://resend.com/docs/api-reference/api-keys/create-api-key); sending-only keys cannot read broadcasts. The source only issues GET requests. Configure `.dlt/secrets.toml`:

```toml
[sources.resend]
api_key = "re_..."
```

Alternatively set `SOURCES__RESEND__API_KEY` or pass `api_key` explicitly. The Resend Python SDK is not required.

| Argument | Default | Behavior |
|---|---|---|
| `sent_only` | `True` | Set to `False` to include all statuses, including drafts and scheduled broadcasts |
| `page_size` | `100` | Number of summaries per request, from 1 to 100 |
| `request_interval` | `0.5` | Non-negative delay in seconds between API calls |

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

For a standalone copy, run this against a branch or release containing the source:

```bash
dlt init resend duckdb --location https://github.com/kingfink/dlt-sources
python resend_pipeline.py
```

For downstream adoption, pin a released package version, update the consumer's dependency declaration and lockfile, configure credentials, and run the consumer pipeline to backfill. Verify loaded HTML/text against the original detail response and reconcile broadcast IDs and row counts across all API pages. If joining to webhook email data, check an actual loaded row on `broadcast_id`. Package release, consumer deployment, data loading, and warehouse model rebuilds are separate steps owned by the downstream repositories.

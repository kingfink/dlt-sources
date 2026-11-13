# resend

Resend dlt source for broadcast metadata, HTML, and plain text. See the repository [installation guide](https://github.com/kingfink/dlt-sources#install) for package and `dlt init` usage.

## Resources

| Resource | Primary key | Write disposition | Notes |
|---|---|---|---|
| `broadcasts` | `broadcast_id` | merge | Sent broadcasts by default |

Every run paginates the [broadcast list](https://resend.com/docs/api-reference/broadcasts/list-broadcasts) and fetches each selected broadcast's [details](https://resend.com/docs/api-reference/broadcasts/get-broadcast). There is no persistent cursor: full rescans capture older drafts that become sent and update existing content. Merge prevents duplicates and retains records deleted upstream. Backfills cover only available API history.

| Column | Type | Notes |
|---|---|---|
| `broadcast_id`, `id` | text | Same Resend identifier; non-null |
| `object`, `name`, `status` | text | Object type, name, status |
| `audience_id`, `segment_id`, `topic_id` | text | Targeting identifiers |
| `from`, `subject`, `preview_text` | text | Sender, subject, preview |
| `html`, `text` | text | Unmodified bodies; nullable |
| `reply_to` | JSON | Reply addresses |
| `created_at`, `scheduled_at`, `sent_at` | timestamp | Source creation and send times |
| `loaded_ts` | timestamp | UTC fetch time; non-null |

Fields are nullable unless marked otherwise. Additional API fields pass through, detail values override summaries, and nested values remain JSON. Null or empty bodies are preserved; responses missing both body fields fail extraction.

Set `sent_only=False` to include all statuses. `page_size` defaults to 100 (range 1–100); `request_interval` defaults to 0.5 seconds between calls. Requests time out after 30 seconds and retry transient failures up to five attempts; unrecoverable failures stop extraction.

## Auth

Configure a [`full_access`](https://resend.com/docs/api-reference/api-keys/create-api-key) API key in `.dlt/secrets.toml`, or set `SOURCES__RESEND__API_KEY`:

```toml
[sources.resend]
api_key = "re_..."
```

## Example

```python
import dlt

from tailor_made_dlt_sources.resend import resend_source

pipeline = dlt.pipeline(
    pipeline_name="resend_demo",
    destination="duckdb",
    dataset_name="resend",
)
info = pipeline.run(resend_source())
print(info)
```

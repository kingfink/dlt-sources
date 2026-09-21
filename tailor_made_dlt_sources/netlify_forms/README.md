# netlify_forms

Netlify Forms dlt source for verified form submissions from one site.

## Resources

| Resource | Primary key | Write disposition | Notes |
|---|---|---|---|
| `form_submissions` | `submission_id` | merge | Complete current submission history, normalized to a stable raw shape |

The source requests every page on each run. Merge loading makes retries and backfills idempotent while retaining previously loaded submissions if they are later deleted from Netlify.

| Column | Type | Notes |
|---|---|---|
| `submission_id` | text | Netlify submission identifier |
| `form_id` | text | Netlify form identifier |
| `form_name` | text | Netlify form name |
| `submitted_ts` | timestamp | Submission creation timestamp |
| `form_data` | text | Stable JSON serialization of submitted fields |
| `loaded_ts` | timestamp | Time the source fetched the submission |

## Auth

Configure credentials in `.dlt/secrets.toml`:

```toml
[sources.netlify_forms]
access_token = "..."
site_id = "..."
```

## Example

```python
import dlt

from tailor_made_dlt_sources.netlify_forms import netlify_forms_source

pipeline = dlt.pipeline(
    pipeline_name="netlify_forms_demo",
    destination="duckdb",
    dataset_name="netlify",
)
info = pipeline.run(netlify_forms_source())
print(info)
```

"""Netlify Forms dlt source."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import dlt

NETLIFY_API_BASE = "https://api.netlify.com/api/v1"
NETLIFY_PAGE_SIZE = 100

FORM_SUBMISSION_COLUMNS = {
    "submission_id": {"data_type": "text", "nullable": False},
    "form_id": {"data_type": "text"},
    "form_name": {"data_type": "text"},
    "submitted_ts": {"data_type": "timestamp"},
    "form_data": {"data_type": "text"},
    "loaded_ts": {"data_type": "timestamp", "nullable": False},
}


def fetch_netlify_form_submissions(
    *,
    access_token: str,
    site_id: str,
    opener=urlopen,
) -> list[dict]:
    """Fetch every verified submission for a Netlify site."""
    submissions = []
    page = 1
    while True:
        query = urlencode({"page": page, "per_page": NETLIFY_PAGE_SIZE})
        request = Request(
            f"{NETLIFY_API_BASE}/sites/{site_id}/submissions?{query}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with opener(request, timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("Netlify submissions response must be a list")
        submissions.extend(batch)
        if len(batch) < NETLIFY_PAGE_SIZE:
            return submissions
        page += 1


def build_submission_rows(
    submissions: list[dict],
    *,
    loaded_ts: datetime,
) -> list[dict]:
    """Normalize Netlify API objects to a stable raw table shape."""
    rows = []
    for submission in submissions:
        submission_id = submission.get("id")
        if not submission_id:
            raise ValueError("Netlify submission is missing id")
        rows.append(
            {
                "submission_id": submission_id,
                "form_id": submission.get("form_id"),
                "form_name": submission.get("form_name"),
                "submitted_ts": submission.get("created_at"),
                "form_data": json.dumps(
                    submission.get("data") or {},
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                "loaded_ts": loaded_ts.isoformat(),
            }
        )
    return rows


def build_netlify_resource(
    dlt_module,
    *,
    access_token: str,
    site_id: str,
    fetcher=fetch_netlify_form_submissions,
    loaded_ts: datetime | None = None,
):
    """Return a merge resource keyed by the Netlify submission ID."""
    loaded_ts = loaded_ts or datetime.now(UTC)

    @dlt_module.resource(
        name="form_submissions",
        primary_key="submission_id",
        write_disposition="merge",
        columns=FORM_SUBMISSION_COLUMNS,
    )
    def form_submissions():
        yield from build_submission_rows(
            fetcher(access_token=access_token, site_id=site_id),
            loaded_ts=loaded_ts,
        )

    return form_submissions()


@dlt.source(name="netlify_forms")
def netlify_forms_source(
    access_token: str = dlt.secrets.value,
    site_id: str = dlt.secrets.value,
):
    """Return verified form submissions for one Netlify site."""
    return build_netlify_resource(
        dlt,
        access_token=access_token,
        site_id=site_id,
    )

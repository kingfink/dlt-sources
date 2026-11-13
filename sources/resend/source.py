"""Extract broadcast metadata and content from the Resend API."""

from __future__ import annotations

import math
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from urllib.parse import quote

import dlt
from dlt.sources.helpers.requests import Client

RESEND_API_BASE = "https://api.resend.com"

BROADCAST_COLUMNS = {
    "broadcast_id": {"data_type": "text", "nullable": False},
    "id": {"data_type": "text", "nullable": False},
    **{
        field: {"data_type": "text"}
        for field in (
            "object",
            "name",
            "audience_id",
            "segment_id",
            "topic_id",
            "from",
            "subject",
            "preview_text",
            "html",
            "text",
            "status",
        )
    },
    "reply_to": {"data_type": "json"},
    "created_at": {"data_type": "timestamp"},
    "scheduled_at": {"data_type": "timestamp"},
    "sent_at": {"data_type": "timestamp"},
    "loaded_ts": {"data_type": "timestamp", "nullable": False},
}


def _validate_options(page_size: int, request_interval: float) -> None:
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
        raise ValueError("page_size must be an integer between 1 and 100")
    if not math.isfinite(request_interval) or request_interval < 0:
        raise ValueError("request_interval must be finite and non-negative")


def _broadcast_id(record: dict) -> str:
    if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"]:
        raise ValueError("Resend broadcast is missing a non-empty string id")
    return record["id"]


def fetch_resend_broadcasts(
    *,
    api_key: str,
    sent_only: bool = True,
    page_size: int = 100,
    request_interval: float = 0.5,
) -> Iterator[dict]:
    """Fetch all available broadcast pages and the full detail of each selected broadcast."""
    _validate_options(page_size, request_interval)
    client = Client(
        request_timeout=30,
        request_max_attempts=5,
        request_backoff_factor=1,
        request_max_retry_delay=60,
        respect_retry_after_header=True,
    )
    with client.session as session:
        session.headers.update({"Authorization": f"Bearer {api_key}"})
        first_request = True

        def get(path: str, **kwargs) -> dict:
            nonlocal first_request
            if not first_request:
                time.sleep(request_interval)
            first_request = False
            with session.get(f"{RESEND_API_BASE}{path}", **kwargs) as response:
                payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Resend response must be an object")
            return payload

        params = {"limit": page_size}
        cursors: set[str] = set()
        seen_ids: set[str] = set()
        while True:
            page = get("/broadcasts", params=params)
            batch = page.get("data")
            has_more = page.get("has_more")
            if not isinstance(batch, list) or not isinstance(has_more, bool):
                raise ValueError("Resend broadcast list must contain data and boolean has_more")
            if has_more and not batch:
                raise ValueError("Resend pagination has_more is true but the page is empty")

            for summary in batch:
                broadcast_id = _broadcast_id(summary)
                if not isinstance(summary.get("status"), str):
                    raise ValueError("Resend broadcast summary is missing status")
                if broadcast_id in seen_ids or (sent_only and summary["status"] != "sent"):
                    continue
                detail = get(f"/broadcasts/{quote(broadcast_id, safe='')}")
                if _broadcast_id(detail) != broadcast_id:
                    raise ValueError("Resend broadcast detail id does not match the requested id")
                if not isinstance(detail.get("status"), str):
                    raise ValueError("Resend broadcast detail is missing status")
                if not any(field in detail for field in ("html", "text")):
                    raise ValueError("Resend broadcast detail is missing html and text fields")
                seen_ids.add(broadcast_id)
                if sent_only and detail["status"] != "sent":
                    continue
                yield {
                    **summary,
                    **detail,
                    "broadcast_id": broadcast_id,
                    "loaded_ts": datetime.now(UTC).isoformat(),
                }

            if not has_more:
                return
            # Advance using the final summary, even when every item on this page was skipped.
            cursor = _broadcast_id(batch[-1])
            if cursor in cursors:
                raise ValueError("Resend pagination cursor did not advance")
            cursors.add(cursor)
            params = {"limit": page_size, "after": cursor}


@dlt.source(name="resend", max_table_nesting=0)
def resend_source(
    api_key: str = dlt.secrets.value,
    sent_only: bool = True,
    page_size: int = 100,
    request_interval: float = 0.5,
):
    """Merge broadcast content by broadcast_id; sent broadcasts are selected by default."""
    _validate_options(page_size, request_interval)

    @dlt.resource(
        name="broadcasts",
        primary_key="broadcast_id",
        write_disposition="merge",
        columns=BROADCAST_COLUMNS,
    )
    def broadcasts():
        yield from fetch_resend_broadcasts(
            api_key=api_key,
            sent_only=sent_only,
            page_size=page_size,
            request_interval=request_interval,
        )

    return broadcasts()

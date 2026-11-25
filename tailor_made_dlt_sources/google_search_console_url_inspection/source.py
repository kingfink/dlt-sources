"""Google Search Console URL Inspection dlt source."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

import dlt

from .auth import SearchConsoleClient, SearchConsoleRateLimitExceeded

logger = logging.getLogger(__name__)

_JSON_COLUMNS: dict[str, dict[str, Any]] = {
    field: {"data_type": "json"}
    for field in (
        "raw_response",
        "sitemap",
        "referring_urls",
        "rich_results_items",
        "amp_result",
        "mobile_usability_result",
    )
}


def _flatten(site_url: str, inspection_url: str, snapshot_date: date, response: dict) -> dict:
    """Flatten an inspect response into a row keyed by site, URL, and snapshot date."""
    result = response.get("inspectionResult", {})
    index_status = result.get("indexStatusResult", {})
    rich_results = result.get("richResultsResult", {})
    return {
        "site_url": site_url,
        "inspection_url": inspection_url,
        "snapshot_date": snapshot_date.isoformat(),
        "inspected_at": datetime.now(UTC).isoformat(),
        "inspection_result_link": result.get("inspectionResultLink"),
        "index_verdict": index_status.get("verdict"),
        "coverage_state": index_status.get("coverageState"),
        "robots_txt_state": index_status.get("robotsTxtState"),
        "indexing_state": index_status.get("indexingState"),
        "page_fetch_state": index_status.get("pageFetchState"),
        "last_crawl_time": index_status.get("lastCrawlTime"),
        "google_canonical": index_status.get("googleCanonical"),
        "user_canonical": index_status.get("userCanonical"),
        "crawled_as": index_status.get("crawledAs"),
        "sitemap": index_status.get("sitemap", []),
        "referring_urls": index_status.get("referringUrls", []),
        "rich_results_verdict": rich_results.get("verdict"),
        "rich_results_items": rich_results.get("detectedItems", []),
        "amp_result": result.get("ampResult"),
        "mobile_usability_result": result.get("mobileUsabilityResult"),
        "raw_response": response,
    }


@dlt.source(name="google_search_console_url_inspection", max_table_nesting=0)
def google_search_console_url_inspection_source(
    site_url: str,
    urls: Iterable[str],
    snapshot_date: date | None = None,
    client_id: str = dlt.secrets.value,
    client_secret: str = dlt.secrets.value,
    refresh_token: str = dlt.secrets.value,
    status: dict | None = None,
):
    """URL Inspection source for a Search Console property.

    Inspections reflect Google's current recorded crawl/index state for a URL,
    not a live test triggered by this call and not a historical backfill --
    Search Console does not expose past inspection results. ``snapshot_date``
    is the observation day; merging on ``(site_url, inspection_url,
    snapshot_date)`` lets same-day retries overwrite without losing prior
    days' rows.
    """
    status = status if status is not None else {}
    snapshot = snapshot_date if snapshot_date is not None else datetime.now(UTC).date()
    client = SearchConsoleClient(client_id, client_secret, refresh_token)
    status["site_url"] = site_url
    status["snapshot_date"] = snapshot.isoformat()
    status.setdefault("inspected_urls", [])

    logger.info(
        "Preparing Search Console URL Inspection source site_url=%s snapshot_date=%s",
        site_url,
        snapshot.isoformat(),
    )

    @dlt.resource(
        name="url_inspections",
        write_disposition="merge",
        primary_key=["site_url", "inspection_url", "snapshot_date"],
        columns=_JSON_COLUMNS,
    )
    def url_inspections():
        for url in urls:
            try:
                response = client.inspect_url(site_url, url)
            except SearchConsoleRateLimitExceeded:
                logger.warning("rate-limited inspecting %s; committing what we have so far", url)
                status["rate_limited_url"] = url
                return
            status["inspected_urls"].append(url)
            yield _flatten(site_url, url, snapshot, response)

    return url_inspections

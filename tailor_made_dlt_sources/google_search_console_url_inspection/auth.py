"""Google Search Console API client helpers for URL Inspection."""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
SEARCH_CONSOLE_INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"


class SearchConsoleRateLimitExceeded(requests.HTTPError):
    """Raised when Search Console 429 retries are exhausted."""


class SearchConsoleRequestError(requests.HTTPError):
    """Raised for non-retryable request failures (auth, malformed request, quota)."""


class SearchConsoleClient:
    """Search Console URL Inspection client with token refresh and retry behavior.

    Only transport, auth, and HTTP-status-level failures are retried or raised
    here. A successful (200) inspection response -- including one reporting a
    FAIL or NEUTRAL indexing verdict -- is returned to the caller as-is; that
    verdict is Google's indexing opinion, not a request error.
    """

    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        if not (client_id and client_secret and refresh_token):
            raise ValueError("client_id, client_secret, and refresh_token are required.")
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._session = requests.Session()

    def _access(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        logger.info("Refreshing Google access token")
        resp = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            timeout=30,
        )
        if not resp.ok:
            _raise_with_body(resp, "/token")
        body = resp.json()
        self._access_token = body["access_token"]
        self._expires_at = time.time() + float(body.get("expires_in", 3600))
        logger.info("Refreshed Google access token expires_in=%s", body.get("expires_in"))
        return self._access_token

    def inspect_url(self, site_url: str, inspection_url: str) -> dict:
        """Call the urlInspection.index:inspect endpoint for one URL."""
        payload = {
            "inspectionUrl": inspection_url,
            "siteUrl": site_url,
            "languageCode": "en-US",
        }
        resp: requests.Response | None = None
        for attempt in range(1, 5):
            headers = {"Authorization": f"Bearer {self._access()}"}
            logger.info(
                "Search Console inspect siteUrl=%s inspectionUrl=%s attempt=%s",
                site_url,
                inspection_url,
                attempt,
            )
            try:
                resp = self._session.post(
                    SEARCH_CONSOLE_INSPECT_URL,
                    headers=headers,
                    json=payload,
                    timeout=60,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                wait = 10 * 2 ** (attempt - 1)
                logger.warning(
                    "Search Console transport error inspectionUrl=%s attempt=%s (%s); sleeping %ds",
                    inspection_url,
                    attempt,
                    type(exc).__name__,
                    wait,
                )
                time.sleep(wait)
                resp = None
                continue

            logger.info(
                "Search Console inspect inspectionUrl=%s attempt=%s status=%s",
                inspection_url,
                attempt,
                resp.status_code,
            )

            if resp.status_code == 401 and attempt == 1:
                logger.warning(
                    "Search Console 401 inspectionUrl=%s; refreshing token and retrying",
                    inspection_url,
                )
                self._access_token = None
                continue
            if resp.status_code == 429:
                wait = _retry_after_seconds(resp)
                logger.warning(
                    "Search Console 429 inspectionUrl=%s; sleeping %ds",
                    inspection_url,
                    wait,
                )
                time.sleep(wait)
                continue
            if 500 <= resp.status_code < 600:
                wait = 10 * 2 ** (attempt - 1)
                logger.warning(
                    "Search Console %d inspectionUrl=%s; sleeping %ds",
                    resp.status_code,
                    inspection_url,
                    wait,
                )
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                _raise_with_body(resp, inspection_url, cls=SearchConsoleRequestError)
            return resp.json()

        if resp is not None and resp.status_code == 429:
            body = resp.text[:500] if resp.text else "<empty body>"
            raise SearchConsoleRateLimitExceeded(
                f"Search Console 429 on {inspection_url} after retries: {body}", response=resp
            )
        if resp is None:
            raise requests.ConnectionError(
                f"Search Console {inspection_url}: transport errors exhausted retries"
            )
        _raise_with_body(resp, inspection_url, cls=SearchConsoleRequestError)


def _retry_after_seconds(resp: requests.Response) -> int:
    raw = resp.headers.get("Retry-After")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return 60


def _raise_with_body(
    resp: requests.Response, inspection_url: str, cls: type[requests.HTTPError] = requests.HTTPError
) -> None:
    body = resp.text[:500] if resp.text else "<empty body>"
    raise cls(
        f"Search Console {resp.status_code} on {inspection_url}: {body}",
        response=resp,
    )

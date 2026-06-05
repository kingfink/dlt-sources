"""Strava API client helpers."""

from __future__ import annotations

import logging
import random
import time

import requests

logger = logging.getLogger(__name__)

STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_READ_WINDOW_SECONDS = 15 * 60


class StravaRateLimitExceeded(requests.HTTPError):
    """Raised when Strava 429 retries are exhausted."""


class StravaClient:
    """GET-only Strava REST client with token refresh and retry behavior."""

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
        logger.info("Refreshing Strava access token")
        resp = requests.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
            },
            timeout=30,
        )
        if not resp.ok:
            _raise_with_body(resp, "/oauth/token")
        body = resp.json()
        self._access_token = body["access_token"]
        self._expires_at = float(body["expires_at"])
        logger.info("Refreshed Strava access token expires_at=%s", self._expires_at)
        if (new_rt := body.get("refresh_token")) and new_rt != self._refresh_token:
            logger.warning("Strava rotated the refresh token; update the configured token.")
            self._refresh_token = new_rt
        return self._access_token

    def get(self, path: str, params: dict | None = None) -> dict | list:
        url = f"{STRAVA_API_BASE}{path}"
        resp: requests.Response | None = None
        for attempt in range(1, 5):
            headers = {"Authorization": f"Bearer {self._access()}"}
            logger.info("Strava GET %s params=%s attempt=%s", path, params or {}, attempt)
            try:
                resp = self._session.get(url, headers=headers, params=params, timeout=60)
            except (requests.ConnectionError, requests.Timeout) as exc:
                wait = 30 * 2 ** (attempt - 1)
                logger.warning(
                    "Strava transport error on %s params=%s attempt=%s (%s); sleeping %ds",
                    path,
                    params or {},
                    attempt,
                    type(exc).__name__,
                    wait,
                )
                time.sleep(wait)
                resp = None
                continue
            logger.info(
                "Strava GET %s params=%s attempt=%s status=%s rate_limit=%s",
                path,
                params or {},
                attempt,
                resp.status_code,
                _rate_limit_headers(resp),
            )

            if resp.status_code == 401 and attempt == 1:
                logger.warning("Strava 401 on %s; refreshing token and retrying", path)
                self._access_token = None
                continue
            if resp.status_code == 429:
                wait = _retry_after_seconds(resp)
                logger.warning(
                    "Strava 429 on %s params=%s; sleeping %ds",
                    path,
                    params or {},
                    wait,
                )
                time.sleep(wait)
                continue
            if 500 <= resp.status_code < 600:
                wait = 30 * 2 ** (attempt - 1)
                logger.warning(
                    "Strava %d on %s params=%s; sleeping %ds",
                    resp.status_code,
                    path,
                    params or {},
                    wait,
                )
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                _raise_with_body(resp, path)
            return resp.json()

        if resp is not None and resp.status_code == 429:
            body = resp.text[:500] if resp.text else "<empty body>"
            raise StravaRateLimitExceeded(
                f"Strava 429 on {path} after retries: {body}", response=resp
            )
        if resp is None:
            raise requests.ConnectionError(f"Strava {path}: transport errors exhausted retries")
        _raise_with_body(resp, path)


def _seconds_to_next_window(now: float | None = None) -> int:
    """Seconds to the next 15-minute wall-clock Strava read window."""
    now = now if now is not None else time.time()
    seconds_into_window = int(now) % STRAVA_READ_WINDOW_SECONDS
    remaining = STRAVA_READ_WINDOW_SECONDS - seconds_into_window
    return remaining + 5 + random.randint(0, 10)


def _retry_after_seconds(resp: requests.Response) -> int:
    raw = resp.headers.get("Retry-After")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return _seconds_to_next_window()


def _rate_limit_headers(resp: requests.Response) -> str:
    limit = resp.headers.get("X-RateLimit-Limit")
    usage = resp.headers.get("X-RateLimit-Usage")
    if limit or usage:
        return f"usage={usage or '?'} limit={limit or '?'}"
    return "unavailable"


def _raise_with_body(resp: requests.Response, path: str) -> None:
    body = resp.text[:500] if resp.text else "<empty body>"
    raise requests.HTTPError(
        f"Strava {resp.status_code} on {path}: {body}",
        response=resp,
    )

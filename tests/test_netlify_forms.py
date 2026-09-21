from __future__ import annotations

import io
import json
from datetime import UTC, datetime

import pytest

from tailor_made_dlt_sources.netlify_forms import (
    FORM_SUBMISSION_COLUMNS,
    build_netlify_resource,
    build_submission_rows,
    fetch_netlify_form_submissions,
)


class FakeHTTPResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


def test_fetches_every_netlify_page() -> None:
    first_page = [{"id": str(index)} for index in range(100)]
    second_page = [{"id": "100"}]
    responses = iter(
        [
            FakeHTTPResponse(json.dumps(first_page).encode()),
            FakeHTTPResponse(json.dumps(second_page).encode()),
        ]
    )
    requests = []

    def opener(request, *, timeout):
        requests.append({"request": request, "timeout": timeout})
        return next(responses)

    submissions = fetch_netlify_form_submissions(
        access_token="secret-token",
        site_id="site-id",
        opener=opener,
    )

    assert len(submissions) == 101
    assert len(requests) == 2
    assert requests[0]["request"].get_header("Authorization") == "Bearer secret-token"
    assert "page=1" in requests[0]["request"].full_url
    assert "page=2" in requests[1]["request"].full_url
    assert requests[0]["timeout"] == 30


def test_builds_stable_raw_rows() -> None:
    rows = build_submission_rows(
        [
            {
                "id": "submission-id",
                "form_id": "form-id",
                "form_name": "newsletter",
                "created_at": "2026-07-21T14:53:49.751Z",
                "data": {
                    "email": "person@example.com",
                    "message": "Hello",
                },
            }
        ],
        loaded_ts=datetime(2026, 7, 22, 16, 30, tzinfo=UTC),
    )

    assert rows == [
        {
            "submission_id": "submission-id",
            "form_id": "form-id",
            "form_name": "newsletter",
            "submitted_ts": "2026-07-21T14:53:49.751Z",
            "form_data": '{"email":"person@example.com","message":"Hello"}',
            "loaded_ts": "2026-07-22T16:30:00+00:00",
        }
    ]


def test_rejects_submission_without_id() -> None:
    with pytest.raises(ValueError, match="missing id"):
        build_submission_rows(
            [{"form_name": "newsletter"}],
            loaded_ts=datetime(2026, 7, 22, tzinfo=UTC),
        )


def test_builds_merge_resource() -> None:
    dlt = FakeDlt()

    resource = build_netlify_resource(
        dlt,
        access_token="secret-token",
        site_id="site-id",
        fetcher=lambda **kwargs: [{"id": "submission-id", "data": {}}],
        loaded_ts=datetime(2026, 7, 22, tzinfo=UTC),
    )

    assert dlt.resource_calls == [
        {
            "name": "form_submissions",
            "primary_key": "submission_id",
            "write_disposition": "merge",
            "columns": FORM_SUBMISSION_COLUMNS,
        }
    ]
    assert list(resource) == [
        {
            "submission_id": "submission-id",
            "form_id": None,
            "form_name": None,
            "submitted_ts": None,
            "form_data": "{}",
            "loaded_ts": "2026-07-22T00:00:00+00:00",
        }
    ]


class FakeDlt:
    def __init__(self) -> None:
        self.resource_calls = []

    def resource(self, **kwargs):
        self.resource_calls.append(kwargs)

        def decorator(func):
            return func

        return decorator

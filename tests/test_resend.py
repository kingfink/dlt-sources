from __future__ import annotations

import json
from datetime import UTC, datetime

import dlt
import pytest
import requests
import responses
from dlt.pipeline.exceptions import PipelineStepFailed

from tailor_made_dlt_sources.resend import RESEND_API_BASE, fetch_resend_broadcasts, resend_source


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    waits = []
    monkeypatch.setattr("tailor_made_dlt_sources.resend.source.time.sleep", waits.append)
    return waits


def _summary(broadcast_id="broadcast-1", status="sent"):
    return {"id": broadcast_id, "status": status, "name": "Newsletter"}


def _detail(broadcast_id="broadcast-1", **overrides):
    return {
        **_summary(broadcast_id),
        "object": "broadcast",
        "audience_id": "audience-1",
        "segment_id": "segment-1",
        "topic_id": None,
        "from": "News <news@example.com>",
        "subject": "00123",
        "preview_text": "This week's news",
        "reply_to": ["reply@example.com", "other@example.com"],
        "html": "<h1>News &amp; café</h1>\r\n<p>{{{contact.first_name|there}}}</p>\n",
        "text": "News & café\r\n{{{contact.first_name|there}}}\n",
        "created_at": "2026-10-01 19:32:22.980+00",
        "scheduled_at": None,
        "sent_at": "2026-11-01 19:32:22.980+00",
        **overrides,
    }


def _page(rsps, data, *, has_more=False, after=None, limit=100):
    params = {"limit": str(limit)}
    if after is not None:
        params["after"] = after
    return rsps.get(
        f"{RESEND_API_BASE}/broadcasts",
        json={"object": "list", "data": data, "has_more": has_more},
        match=[responses.matchers.query_param_matcher(params)],
    )


def _stub_detail(rsps, broadcast_id="broadcast-1", **overrides):
    return rsps.get(
        f"{RESEND_API_BASE}/broadcasts/{broadcast_id}",
        json=_detail(broadcast_id, **overrides),
    )


def _fetch(**kwargs):
    return list(fetch_resend_broadcasts(api_key="secret-token", **kwargs))


def test_follows_cursors_through_unsent_pages_and_fetches_each_detail_once():
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary(), _summary("draft-1", "draft")], has_more=True)
        _stub_detail(rsps)
        _page(
            rsps,
            [_summary("scheduled-1", "scheduled")],
            has_more=True,
            after="draft-1",
        )
        _page(rsps, [_summary("broadcast-2"), _summary()], after="scheduled-1")
        _stub_detail(rsps, "broadcast-2")

        rows = _fetch()

        assert [row["broadcast_id"] for row in rows] == ["broadcast-1", "broadcast-2"]
        assert len(rsps.calls) == 5
        assert all(
            call.request.headers["Authorization"] == "Bearer secret-token" for call in rsps.calls
        )


@pytest.mark.parametrize("text", [None, "", "Plain text\r\nwith whitespace \n"])
def test_preserves_original_content_and_metadata_with_real_fetch_time(text):
    detail = _detail(text=text, extra={"nested": ["unmodified", 1]})
    before = datetime.now(UTC)
    with responses.RequestsMock() as rsps:
        _page(rsps, [{**_summary(), "name": "Old name", "summary_only": "keep"}])
        rsps.get(f"{RESEND_API_BASE}/broadcasts/broadcast-1", json=detail)
        [row] = _fetch()
    after = datetime.now(UTC)

    assert before <= datetime.fromisoformat(row.pop("loaded_ts")) <= after
    assert row == {**detail, "summary_only": "keep", "broadcast_id": "broadcast-1"}


def test_terminal_full_page_does_not_trigger_another_request():
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary()], limit=1)
        _stub_detail(rsps)
        assert len(_fetch(page_size=1)) == 1


def test_can_include_unsent_broadcasts_and_preserve_null_bodies():
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary("draft", "draft")])
        _stub_detail(rsps, "draft", status="draft", sent_at=None, html=None, text=None)
        [row] = _fetch(sent_only=False)
    assert row["status"] == "draft"
    assert row["sent_at"] is row["html"] is row["text"] is None


def test_rechecks_status_in_detail():
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary()])
        _stub_detail(rsps, status="draft", sent_at=None)
        assert _fetch() == []


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "must be an object"),
        ({"data": []}, "boolean has_more"),
        ({"data": [], "has_more": True}, "page is empty"),
        ({"data": [{"status": "sent"}], "has_more": False}, "missing.*id"),
        ({"data": [{"id": "x"}], "has_more": False}, "missing status"),
    ],
)
def test_rejects_malformed_list_instead_of_silent_truncation(payload, message):
    with responses.RequestsMock() as rsps:
        rsps.get(f"{RESEND_API_BASE}/broadcasts", json=payload)
        with pytest.raises(ValueError, match=message):
            _fetch()


@pytest.mark.parametrize(
    "detail, message",
    [
        (_detail("wrong-id"), "does not match"),
        ({"id": "broadcast-1", "status": "sent"}, "missing html and text"),
        ({"id": "broadcast-1", "html": "body"}, "missing status"),
    ],
)
def test_rejects_incomplete_or_mismatched_detail(detail, message):
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary()])
        rsps.get(f"{RESEND_API_BASE}/broadcasts/broadcast-1", json=detail)
        with pytest.raises(ValueError, match=message):
            _fetch()


def test_rejects_repeated_pagination_cursor():
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary("draft", "draft")], has_more=True)
        _page(rsps, [_summary("draft", "draft")], has_more=True, after="draft")
        with pytest.raises(ValueError, match="cursor did not advance"):
            _fetch()
        assert len(rsps.calls) == 2


def test_retries_rate_limited_list_using_retry_after(sleeps):
    with responses.RequestsMock() as rsps:
        rsps.get(f"{RESEND_API_BASE}/broadcasts", status=429, headers={"Retry-After": "3"})
        _page(rsps, [_summary()])
        _stub_detail(rsps)
        [row] = _fetch(request_interval=0)
        assert row["broadcast_id"] == "broadcast-1"
        assert len(rsps.calls) == 3
    assert 3 in sleeps


@pytest.mark.parametrize(
    "failure",
    [
        {"status": 503},
        {"body": requests.ConnectionError("connection lost")},
        {"body": requests.Timeout("timed out")},
    ],
)
def test_retries_transient_detail_failures(failure):
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary()])
        rsps.get(f"{RESEND_API_BASE}/broadcasts/broadcast-1", **failure)
        _stub_detail(rsps)
        assert len(_fetch()) == 1
        assert len(rsps.calls) == 3


@pytest.mark.parametrize("status, attempts", [(403, 1), (429, 5), (503, 5)])
def test_failed_details_are_not_silently_skipped(status, attempts):
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary()])
        failure = rsps.get(f"{RESEND_API_BASE}/broadcasts/broadcast-1", status=status)
        with pytest.raises(requests.HTTPError):
            _fetch()
        assert failure.call_count == attempts


def test_paces_successful_requests(sleeps):
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary(), _summary("broadcast-2")])
        _stub_detail(rsps)
        _stub_detail(rsps, "broadcast-2")
        _fetch(request_interval=0.75)
    assert sleeps == [0.75, 0.75]


@pytest.mark.parametrize(
    "options",
    [
        {"page_size": 0},
        {"page_size": 101},
        {"request_interval": -1},
        {"request_interval": float("nan")},
    ],
)
def test_rejects_invalid_options_before_extraction(options):
    with pytest.raises(ValueError):
        resend_source(api_key="secret-token", **options)


def test_source_can_be_constructed_without_network_and_resolves_secret(monkeypatch):
    monkeypatch.setenv("SOURCES__RESEND__API_KEY", "configured-token")
    with responses.RequestsMock() as rsps:
        source = resend_source()
        assert source.name == "resend"
        assert list(source.resources.selected) == ["broadcasts"]
        assert len(rsps.calls) == 0
        _page(rsps, [])
        assert list(source) == []
        assert rsps.calls[0].request.headers["Authorization"] == "Bearer configured-token"


def _pipeline(tmp_path):
    return dlt.pipeline(
        pipeline_name="resend_test",
        destination=dlt.destinations.duckdb(str(tmp_path / "resend.duckdb")),
        dataset_name="resend_test",
        pipelines_dir=str(tmp_path / "pipelines"),
    )


def _source():
    return resend_source(api_key="secret-token", request_interval=0)


def test_merge_backfills_updates_adds_and_retains_absent_broadcasts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pipeline = _pipeline(tmp_path)
    before = datetime.now(UTC)
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary(), _summary("retained"), _summary("old-draft", "draft")])
        _stub_detail(rsps, extra={"nested": [1, 2]})
        _stub_detail(rsps, "retained", text=None)
        assert not pipeline.run(_source()).has_failed_jobs

    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary("new"), _summary(), _summary("old-draft")])
        _stub_detail(rsps, "new")
        _stub_detail(rsps, html="<p>Updated content</p>", text="Updated content")
        _stub_detail(rsps, "old-draft")
        assert not pipeline.run(_source()).has_failed_jobs
        # Retry the same extraction against the same destination.
        assert not pipeline.run(_source()).has_failed_jobs

    with pipeline.sql_client() as client:
        assert client.execute_sql(
            "SELECT broadcast_id, COUNT(*) FROM broadcasts GROUP BY 1 ORDER BY 1"
        ) == [("broadcast-1", 1), ("new", 1), ("old-draft", 1), ("retained", 1)]
        assert client.execute_sql(
            "SELECT id, subject, html, text FROM broadcasts WHERE broadcast_id = 'broadcast-1'"
        ) == [("broadcast-1", "00123", "<p>Updated content</p>", "Updated content")]
        [(reply_to, loaded_ts, sent_at)] = client.execute_sql(
            "SELECT reply_to, loaded_ts, sent_at FROM broadcasts WHERE broadcast_id = 'broadcast-1'"
        )
        assert json.loads(reply_to) == _detail()["reply_to"]
        assert before <= loaded_ts <= datetime.now(UTC)
        assert sent_at.isoformat() == "2026-11-01T19:32:22.980000+00:00"
        assert client.execute_sql(
            "SELECT html, text FROM broadcasts WHERE broadcast_id = 'retained'"
        ) == [(_detail()["html"], None)]
        names = {
            row[0]
            for row in client.execute_sql(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'resend_test'"
            )
        }
        assert not any(name.startswith("broadcasts__") for name in names)


def test_failed_later_page_can_be_rerun_without_losing_or_duplicating_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pipeline = _pipeline(tmp_path)
    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary()], has_more=True)
        _stub_detail(rsps)
        rsps.get(
            f"{RESEND_API_BASE}/broadcasts",
            status=503,
            match=[
                responses.matchers.query_param_matcher({"limit": "100", "after": "broadcast-1"})
            ],
        )
        with pytest.raises(PipelineStepFailed):
            pipeline.run(_source())

    with responses.RequestsMock() as rsps:
        _page(rsps, [_summary()], has_more=True)
        _stub_detail(rsps)
        _page(rsps, [_summary("broadcast-2")], after="broadcast-1")
        _stub_detail(rsps, "broadcast-2")
        assert not pipeline.run(_source()).has_failed_jobs
        assert not pipeline.run(_source()).has_failed_jobs

    with pipeline.sql_client() as client:
        assert client.execute_sql(
            "SELECT broadcast_id, COUNT(*) FROM broadcasts GROUP BY 1 ORDER BY 1"
        ) == [("broadcast-1", 1), ("broadcast-2", 1)]

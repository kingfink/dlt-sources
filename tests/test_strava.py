from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import dlt
import requests
import responses

from tailor_made_dlt_sources.strava import (
    STRAVA_API_BASE,
    STRAVA_READ_WINDOW_SECONDS,
    STRAVA_TOKEN_URL,
    StravaClient,
    _retry_after_seconds,
    _seconds_to_next_window,
    strava_source,
)

SINCE = datetime(2024, 1, 1, tzinfo=UTC)
UNTIL = datetime(2024, 2, 1, tzinfo=UTC)


def test_source_loads_to_duckdb_without_child_tables(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with _stub_strava():
        pipeline = _make_pipeline(tmp_path)
        info = pipeline.run(
            strava_source(
                client_id="cid",
                client_secret="csec",
                refresh_token="rt",
                since=SINCE,
                until=UNTIL,
            )
        )

    assert info.has_failed_jobs is False
    with pipeline.sql_client() as c:
        assert c.execute_sql("SELECT COUNT(*) FROM activities")[0][0] == 2
        names = {
            r[0]
            for r in c.execute_sql(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'strava_test'"
            )
        }
        assert not any(t.startswith("activities__") for t in names), names


def test_graceful_exit_on_rate_limit_records_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tailor_made_dlt_sources.strava.auth.time.sleep", lambda *_: None)
    pipeline = _make_pipeline(tmp_path)

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _stub_token(rsps)
        _stub_summary_list(
            rsps,
            [
                {"id": 1001, "start_date": "2024-01-01T10:00:00Z", "name": "Morning Run"},
                {"id": 1002, "start_date": "2024-01-02T10:00:00Z", "name": "Evening Ride"},
            ],
        )
        _stub_detail(rsps, 1001)
        rsps.get(
            f"{STRAVA_API_BASE}/activities/1002",
            json={"message": "Rate Limit Exceeded"},
            status=429,
        )

        status = {}
        info = pipeline.run(
            strava_source(
                client_id="cid",
                client_secret="csec",
                refresh_token="rt",
                since=SINCE,
                until=UNTIL,
                status=status,
            )
        )

    assert info.has_failed_jobs is False
    assert status["rate_limited_path"] == "/activities/1002"
    assert status["extracted_activity_ids"] == [1001]
    with pipeline.sql_client() as c:
        assert c.execute_sql("SELECT id FROM activities") == [(1001,)]


def test_detail_cache_skips_duplicate_detail_fetches(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = _make_pipeline(tmp_path, name="strava_first", pipelines_dir=tmp_path / "first")
    second = _make_pipeline(tmp_path, name="strava_second", pipelines_dir=tmp_path / "second")
    detail_cache = {}

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _stub_token(rsps)
        _stub_summary_list(
            rsps,
            [
                {"id": 1001, "start_date": "2024-01-01T10:00:00Z", "name": "Morning Run"},
                {"id": 1002, "start_date": "2024-01-02T10:00:00Z", "name": "Evening Ride"},
            ],
        )
        detail_1001 = _stub_detail(rsps, 1001)
        detail_1002 = _stub_detail(rsps, 1002)

        first_status = {}
        first.run(
            strava_source(
                client_id="cid",
                client_secret="csec",
                refresh_token="rt",
                since=SINCE,
                until=UNTIL,
                status=first_status,
                detail_cache=detail_cache,
            )
        )
        second_status = {}
        second.run(
            strava_source(
                client_id="cid",
                client_secret="csec",
                refresh_token="rt",
                since=SINCE,
                until=UNTIL,
                status=second_status,
                detail_cache=detail_cache,
            )
        )

    assert detail_1001.call_count == 1
    assert detail_1002.call_count == 1
    assert sorted(second_status["cache_hit_activity_ids"]) == [1001, 1002]


def test_get_retries_on_connection_error(monkeypatch):
    monkeypatch.setattr("tailor_made_dlt_sources.strava.auth.time.sleep", lambda *_: None)

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _stub_token(rsps)
        rsps.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            body=requests.ConnectionError("Remote end closed connection"),
        )
        rsps.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            json=[{"id": 1, "start_date": "2024-01-01T10:00:00Z"}],
        )

        client = StravaClient("c", "s", "rt")
        assert client.get("/athlete/activities") == [
            {"id": 1, "start_date": "2024-01-01T10:00:00Z"}
        ]


def test_seconds_to_next_window_aligns_to_15min_boundary():
    boundary = 1_700_000_000 - (1_700_000_000 % STRAVA_READ_WINDOW_SECONDS)

    wait = _seconds_to_next_window(boundary + 1)
    assert STRAVA_READ_WINDOW_SECONDS - 1 + 5 <= wait <= STRAVA_READ_WINDOW_SECONDS - 1 + 15
    wait = _seconds_to_next_window(boundary + STRAVA_READ_WINDOW_SECONDS - 60)
    assert 65 <= wait <= 75


def test_retry_after_header_is_honored():
    assert _retry_after_seconds(SimpleNamespace(headers={"Retry-After": "42"})) == 42
    assert _retry_after_seconds(SimpleNamespace(headers={"Retry-After": "junk"})) >= 5
    assert _retry_after_seconds(SimpleNamespace(headers={})) >= 5


def _make_pipeline(tmp_path, name="strava_test", pipelines_dir=None) -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name=name,
        destination=dlt.destinations.duckdb(str(tmp_path / "test.duckdb")),
        dataset_name="strava_test",
        pipelines_dir=str(pipelines_dir or tmp_path / "pipelines"),
    )


def _stub_strava():
    rsps = responses.RequestsMock(assert_all_requests_are_fired=False)
    rsps.start()
    _stub_token(rsps)
    _stub_summary_list(
        rsps,
        [
            {"id": 1001, "start_date": "2024-01-01T10:00:00Z", "name": "Morning Run"},
            {"id": 1002, "start_date": "2024-01-02T10:00:00Z", "name": "Evening Ride"},
        ],
    )
    _stub_detail(rsps, 1001, start_date="2024-01-01T10:00:00Z", name="Morning Run")
    _stub_detail(
        rsps,
        1002,
        start_date="2024-01-02T10:00:00Z",
        name="Evening Ride",
        distance=20000.0,
    )
    return rsps


def _stub_token(rsps):
    rsps.post(
        STRAVA_TOKEN_URL,
        json={
            "access_token": "fake-access",
            "refresh_token": "rt",
            "expires_at": 9999999999,
            "expires_in": 21600,
            "token_type": "Bearer",
        },
    )


def _stub_summary_list(rsps, summaries):
    rsps.get(f"{STRAVA_API_BASE}/athlete/activities", json=summaries)


def _stub_detail(rsps, activity_id, **extra):
    return rsps.get(
        f"{STRAVA_API_BASE}/activities/{activity_id}",
        json={
            "id": activity_id,
            "start_date": extra.pop("start_date", "2024-01-01T10:00:00Z"),
            "name": extra.pop("name", f"Activity {activity_id}"),
            "distance": extra.pop("distance", 5000.0),
            "splits_metric": [],
            "laps": [],
            "map": {"polyline": "abc"},
            **extra,
        },
    )

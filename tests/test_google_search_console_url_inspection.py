from __future__ import annotations

from datetime import date

import dlt
import requests
import responses

from tailor_made_dlt_sources.google_search_console_url_inspection import (
    GOOGLE_TOKEN_URL,
    SEARCH_CONSOLE_INSPECT_URL,
    SearchConsoleClient,
    SearchConsoleRequestError,
    google_search_console_url_inspection_source,
)

SITE_URL = "https://example.com/"
SNAPSHOT = date(2024, 1, 1)


def test_source_loads_to_duckdb_without_child_tables(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pipeline = _make_pipeline(tmp_path)

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _stub_token(rsps)
        _stub_inspect(rsps, "https://example.com/", verdict="PASS")
        _stub_inspect(rsps, "https://example.com/about", verdict="NEUTRAL")

        info = pipeline.run(
            google_search_console_url_inspection_source(
                site_url=SITE_URL,
                urls=["https://example.com/", "https://example.com/about"],
                snapshot_date=SNAPSHOT,
                client_id="cid",
                client_secret="csec",
                refresh_token="rt",
            )
        )

    assert info.has_failed_jobs is False
    with pipeline.sql_client() as c:
        assert c.execute_sql("SELECT COUNT(*) FROM url_inspections")[0][0] == 2
        rows = c.execute_sql(
            "SELECT inspection_url, index_verdict, snapshot_date FROM url_inspections "
            "ORDER BY inspection_url"
        )
        assert rows[0][0] == "https://example.com/"
        assert rows[0][1] == "PASS"
        assert str(rows[0][2]) == "2024-01-01"
        assert rows[1][1] == "NEUTRAL"
        names = {
            r[0]
            for r in c.execute_sql(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'gsc_url_inspection_test'"
            )
        }
        assert not any(t.startswith("url_inspections__") for t in names), names


def test_same_day_retry_merges_instead_of_duplicating(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pipeline = _make_pipeline(tmp_path)

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _stub_token(rsps)
        _stub_inspect(rsps, "https://example.com/", verdict="NEUTRAL")
        pipeline.run(
            google_search_console_url_inspection_source(
                site_url=SITE_URL,
                urls=["https://example.com/"],
                snapshot_date=SNAPSHOT,
                client_id="cid",
                client_secret="csec",
                refresh_token="rt",
            )
        )
        _stub_inspect(rsps, "https://example.com/", verdict="PASS")
        pipeline.run(
            google_search_console_url_inspection_source(
                site_url=SITE_URL,
                urls=["https://example.com/"],
                snapshot_date=SNAPSHOT,
                client_id="cid",
                client_secret="csec",
                refresh_token="rt",
            )
        )

    with pipeline.sql_client() as c:
        rows = c.execute_sql("SELECT index_verdict FROM url_inspections")
        assert rows == [("PASS",)]


def test_different_snapshot_date_keeps_earlier_day(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pipeline = _make_pipeline(tmp_path)

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _stub_token(rsps)
        _stub_inspect(rsps, "https://example.com/", verdict="PASS")
        pipeline.run(
            google_search_console_url_inspection_source(
                site_url=SITE_URL,
                urls=["https://example.com/"],
                snapshot_date=date(2024, 1, 1),
                client_id="cid",
                client_secret="csec",
                refresh_token="rt",
            )
        )
        _stub_inspect(rsps, "https://example.com/", verdict="FAIL")
        pipeline.run(
            google_search_console_url_inspection_source(
                site_url=SITE_URL,
                urls=["https://example.com/"],
                snapshot_date=date(2024, 1, 2),
                client_id="cid",
                client_secret="csec",
                refresh_token="rt",
            )
        )

    with pipeline.sql_client() as c:
        assert c.execute_sql("SELECT COUNT(*) FROM url_inspections")[0][0] == 2


def test_graceful_exit_on_rate_limit_records_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "tailor_made_dlt_sources.google_search_console_url_inspection.auth.time.sleep",
        lambda *_: None,
    )
    pipeline = _make_pipeline(tmp_path)

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _stub_token(rsps)
        _stub_inspect(rsps, "https://example.com/", verdict="PASS")
        for _ in range(4):
            rsps.post(
                SEARCH_CONSOLE_INSPECT_URL,
                json={"error": {"message": "Quota exceeded"}},
                status=429,
            )

        status = {}
        info = pipeline.run(
            google_search_console_url_inspection_source(
                site_url=SITE_URL,
                urls=["https://example.com/", "https://example.com/about"],
                snapshot_date=SNAPSHOT,
                client_id="cid",
                client_secret="csec",
                refresh_token="rt",
                status=status,
            )
        )

    assert info.has_failed_jobs is False
    assert status["rate_limited_url"] == "https://example.com/about"
    assert status["inspected_urls"] == ["https://example.com/"]
    with pipeline.sql_client() as c:
        assert c.execute_sql("SELECT COUNT(*) FROM url_inspections")[0][0] == 1


def test_request_error_raises_instead_of_dropping_url(monkeypatch):
    monkeypatch.setattr(
        "tailor_made_dlt_sources.google_search_console_url_inspection.auth.time.sleep",
        lambda *_: None,
    )
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _stub_token(rsps)
        rsps.post(
            SEARCH_CONSOLE_INSPECT_URL,
            json={"error": {"message": "Invalid argument"}},
            status=400,
        )
        client = SearchConsoleClient("c", "s", "rt")
        try:
            client.inspect_url(SITE_URL, "https://example.com/")
        except SearchConsoleRequestError:
            pass
        else:
            raise AssertionError("expected SearchConsoleRequestError")


def test_get_retries_on_connection_error(monkeypatch):
    monkeypatch.setattr(
        "tailor_made_dlt_sources.google_search_console_url_inspection.auth.time.sleep",
        lambda *_: None,
    )
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _stub_token(rsps)
        rsps.post(
            SEARCH_CONSOLE_INSPECT_URL,
            body=requests.ConnectionError("Remote end closed connection"),
        )
        _stub_inspect(rsps, "https://example.com/", verdict="PASS")

        client = SearchConsoleClient("c", "s", "rt")
        result = client.inspect_url(SITE_URL, "https://example.com/")
        assert result["inspectionResult"]["indexStatusResult"]["verdict"] == "PASS"


def _make_pipeline(tmp_path, name="gsc_url_inspection_test", pipelines_dir=None) -> dlt.Pipeline:
    return dlt.pipeline(
        pipeline_name=name,
        destination=dlt.destinations.duckdb(str(tmp_path / "test.duckdb")),
        dataset_name="gsc_url_inspection_test",
        pipelines_dir=str(pipelines_dir or tmp_path / "pipelines"),
    )


def _stub_token(rsps):
    rsps.post(
        GOOGLE_TOKEN_URL,
        json={
            "access_token": "fake-access",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
    )


def _stub_inspect(rsps, inspection_url, verdict="PASS", rich_results_verdict="PASS"):
    return rsps.post(
        SEARCH_CONSOLE_INSPECT_URL,
        json={
            "inspectionResult": {
                "inspectionResultLink": f"https://search.google.com/link?q={inspection_url}",
                "indexStatusResult": {
                    "verdict": verdict,
                    "coverageState": "Submitted and indexed",
                    "robotsTxtState": "ALLOWED",
                    "indexingState": "INDEXING_ALLOWED",
                    "pageFetchState": "SUCCESSFUL",
                    "lastCrawlTime": "2023-12-31T00:00:00Z",
                    "googleCanonical": inspection_url,
                    "userCanonical": inspection_url,
                    "crawledAs": "DESKTOP",
                    "sitemap": ["https://example.com/sitemap.xml"],
                    "referringUrls": [],
                },
                "richResultsResult": {
                    "verdict": rich_results_verdict,
                    "detectedItems": [],
                },
            }
        },
    )

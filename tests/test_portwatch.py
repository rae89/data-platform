import dlt
import duckdb
import pytest

from data_platform.defs.sources.portwatch import loads


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


def fake_api(pages, calls):
    """Serves `pages` in order, recording each request. A page is a list of rows, or
    (rows, True) when the API should report that more pages follow."""

    def get(url, params, timeout):
        calls.append(params)
        page = pages[len(calls) - 1]
        rows, more = page if isinstance(page, tuple) else (page, False)
        return FakeResponse(
            {"features": [{"attributes": {**r, "ObjectId": 1}} for r in rows], "exceededTransferLimit": more}
        )

    return get


def day(d, calls=1):
    return {"portid": "port664", "date": d, "portcalls": calls}


def run(tmp_path, monkeypatch, pages, ports=None):
    calls = []
    monkeypatch.setattr(loads.requests, "get", fake_api(pages, calls))
    pipeline = dlt.pipeline(
        "portwatch_test",
        destination=dlt.destinations.duckdb(str(tmp_path / "w.duckdb")),
        dataset_name="portwatch",
        pipelines_dir=str(tmp_path / ".dlt"),
    )
    source = loads.portwatch()
    if ports:
        source.daily_ports.bind(ports=ports)
    source.max_table_nesting = 0
    pipeline.run(source)
    return calls


def test_pages_then_loads_incrementally_with_lookback(tmp_path, monkeypatch):
    first = run(tmp_path, monkeypatch, [([day("2026-10-01"), day("2026-10-02")], True), [day("2026-10-20")]])
    assert [c["resultOffset"] for c in first] == [0, 2]  # follows exceededTransferLimit
    assert "date >= '2019-01-01'" in first[0]["where"] and "portid = 'port664'" in first[0]["where"]

    # Next run starts 14 days before the newest loaded day, and revisions merge by (port, date).
    second = run(tmp_path, monkeypatch, [[day("2026-10-20", calls=5), day("2026-10-21")]])
    assert "date >= '2026-10-06'" in second[0]["where"]

    with duckdb.connect(str(tmp_path / "w.duckdb"), read_only=True) as conn:
        rows = conn.execute("select date, portcalls from portwatch.daily_ports order by date").fetchall()
        columns = {r[0] for r in conn.execute(
            "select column_name from information_schema.columns where table_name = 'daily_ports'"
        ).fetchall()}
    assert rows == [("2026-10-01", 1), ("2026-10-02", 1), ("2026-10-20", 5), ("2026-10-21", 1)]
    assert "objectid" not in columns  # ArcGIS's internal row id is dropped


def test_api_errors_fail_the_load(tmp_path, monkeypatch):
    monkeypatch.setattr(loads.requests, "get", lambda url, params, timeout: FakeResponse({"error": {"code": 400}}))
    with pytest.raises(Exception, match="PortWatch API error"):
        run_pipeline = dlt.pipeline(
            "portwatch_err",
            destination=dlt.destinations.duckdb(str(tmp_path / "e.duckdb")),
            pipelines_dir=str(tmp_path / ".dlt"),
        )
        run_pipeline.run(loads.portwatch())


def test_no_new_days_keeps_the_cursor(tmp_path, monkeypatch):
    run(tmp_path, monkeypatch, [[day("2026-10-20")]])
    assert "date >= '2026-10-06'" in run(tmp_path, monkeypatch, [[]])[0]["where"]
    # Nothing new arrived, so the next run still looks back from 2026-10-20.
    assert "date >= '2026-10-06'" in run(tmp_path, monkeypatch, [[]])[0]["where"]


def test_a_newly_added_port_backfills_from_the_start(tmp_path, monkeypatch):
    run(tmp_path, monkeypatch, [[day("2026-10-20")]])
    calls = run(tmp_path, monkeypatch, [[], [{**day("2026-10-21"), "portid": "port815"}]],
                ports={"port664": "LA-LB", "port815": "NY-NJ"})
    assert "portid = 'port664' AND date >= '2026-10-06'" in calls[0]["where"]  # lookback
    assert "portid = 'port815' AND date >= '2019-01-01'" in calls[1]["where"]  # full history

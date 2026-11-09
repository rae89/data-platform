import importlib

import dagster as dg

from data_platform.definitions import defs


def test_definitions_load_every_asset_job_and_sensor():
    # Needs the dbt manifest state: run `just defs-state` first.
    loaded = defs()
    repo = loaded.get_repository_def()

    assert {k.to_user_string() for k in repo.asset_graph.get_all_asset_keys()} == {
        "bi/marts_snapshot",
        "portwatch/daily_ports",
        "staging/stg_portwatch__daily_ports",
        "marts/port_daily_activity",
        "portwatch/daily_chokepoints",
        "staging/stg_portwatch__daily_chokepoints",
        "marts/port_monthly_trade",
        "marts/chokepoint_monthly_transits",
    }
    # The BI snapshot runs after every mart it copies.
    graph = repo.asset_graph
    snapshot = dg.AssetKey(["bi", "marts_snapshot"])
    marts = {k for k in graph.get_all_asset_keys() if k.path[0] == "marts"}
    assert set(graph.get(snapshot).parent_keys) == marts  # every mart triggers and gates it
    # Groups follow the layers: dlt loads, dbt staging, dbt marts, the BI copy.
    layer = {"portwatch": "source", "staging": "transform", "marts": "metrics", "bi": "serve"}
    assert all(graph.get(k).group_name == layer[k.path[0]] for k in graph.get_all_asset_keys())
    # The daily job builds everything except the snapshot, which runs on its own (defs/bi.py).
    job_keys = repo.get_job("ingest_sources").asset_layer.executable_asset_keys
    assert job_keys == set(graph.get_all_asset_keys()) - {snapshot}
    assert {s.name for s in loaded.schedules} == {"ingest_sources_schedule"}
    assert {s.name for s in loaded.sensors} == {
        "asset_sli",
        "run_success_sli",
        "run_failure_sli",
        "serve_automation",
    }
    assert loaded.executor == dg.in_process_executor  # DuckDB allows one writer process


def test_duckdb_path_defaults_to_repo_data_dir(monkeypatch):
    import data_platform.defs.resources as resources

    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    reloaded = importlib.reload(resources)
    assert reloaded.DUCKDB_PATH.endswith("data/warehouse.duckdb")
    assert (reloaded.Path(reloaded.DUCKDB_PATH).parents[1] / "pyproject.toml").exists()

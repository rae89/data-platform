import importlib

import dagster as dg

from data_platform.definitions import defs


def test_definitions_load_every_asset_job_and_sensor():
    # Needs the dbt manifest state: run `just defs-state` first.
    loaded = defs()
    repo = loaded.get_repository_def()

    assert {k.to_user_string() for k in repo.asset_graph.get_all_asset_keys()} == {
        "raw/customers",
        "raw/orders",
        "staging/stg_customers",
        "staging/stg_orders",
        "marts/customer_orders",
        "marts/daily_revenue",
        "bi/marts_snapshot",
    }
    # The BI snapshot runs after every mart it copies.
    graph = repo.asset_graph
    snapshot = dg.AssetKey(["bi", "marts_snapshot"])
    assert {k.to_user_string() for k in graph.get(snapshot).parent_keys} == {
        "marts/customer_orders",
        "marts/daily_revenue",
    }
    assert repo.has_job("refresh_all")
    # The snapshot runs on its own (see defs/bi.py), never inside refresh_all.
    job_keys = repo.get_job("refresh_all").asset_layer.executable_asset_keys
    assert job_keys == set(graph.get_all_asset_keys()) - {snapshot}
    assert {s.name for s in loaded.schedules} == {"refresh_all_schedule"}
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

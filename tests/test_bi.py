from pathlib import Path

import dagster as dg
import duckdb
from dagster_duckdb import DuckDBResource

from data_platform.defs import bi


def make_warehouse(path, orders_rows):
    with duckdb.connect(str(path)) as conn:
        conn.execute("create schema marts")
        conn.execute("create table marts.customer_orders as select 1 as customer_id")
        conn.execute(f"create table marts.daily_revenue as select * from range({orders_rows}) t(d)")


def snapshot(warehouse, instance):
    resources = {"duckdb": DuckDBResource(database=str(warehouse))}
    result = dg.materialize([bi.bi_marts_snapshot], resources=resources, instance=instance)
    return result.asset_materializations_for_node("bi__marts_snapshot")[0].metadata


def test_snapshot_copies_marts_and_never_blocks_on_readers(tmp_path, monkeypatch):
    warehouse = tmp_path / "warehouse.duckdb"
    target = tmp_path / "bi.duckdb"
    monkeypatch.setattr(bi, "BI_DUCKDB_PATH", target)
    make_warehouse(warehouse, orders_rows=3)

    with dg.instance_for_test() as instance:
        assert snapshot(warehouse, instance)["rows_copied"].value == 1 + 3

        # A BI query holds the snapshot open while the next run replaces it.
        reader = duckdb.connect(str(target), read_only=True)
        with duckdb.connect(str(warehouse)) as conn:
            conn.execute("insert into marts.daily_revenue select 99")
        assert snapshot(warehouse, instance)["rows_copied"].value == 1 + 4
        assert reader.execute("select count(*) from marts.daily_revenue").fetchone()[0] == 3
        reader.close()

    with duckdb.connect(str(target), read_only=True) as conn:
        assert conn.execute("select count(*) from marts.daily_revenue").fetchone()[0] == 4
        assert not (tmp_path / "bi.duckdb.tmp").exists()


def test_snapshot_path_sits_next_to_the_warehouse():
    from data_platform.defs.resources import DUCKDB_PATH

    assert bi.BI_DUCKDB_PATH.parent == Path(DUCKDB_PATH).parent
    assert bi.BI_DUCKDB_PATH.name == "bi.duckdb"


def test_snapshot_copies_new_marts_and_survives_a_crashed_run(tmp_path, monkeypatch):
    # A quote in the path must not break the ATTACH statement.
    folder = tmp_path / "o'brien"
    folder.mkdir()
    warehouse, target = folder / "warehouse.duckdb", folder / "bi.duckdb"
    monkeypatch.setattr(bi, "BI_DUCKDB_PATH", target)
    make_warehouse(warehouse, orders_rows=2)
    with duckdb.connect(str(warehouse)) as conn:
        conn.execute("create table marts.product_sales as select 7 as units")  # a new mart
    # Leftovers from a run killed mid-copy.
    (folder / "bi.duckdb.tmp").write_bytes(b"partial")
    (folder / "bi.duckdb.tmp.wal").write_bytes(b"stale wal")

    with dg.instance_for_test() as instance:
        meta = snapshot(warehouse, instance)
    assert meta["tables"].value == 3
    assert "dagster/row_count" not in meta  # would double-count rows in the SLIs
    with duckdb.connect(str(target), read_only=True) as conn:
        assert conn.execute("select units from marts.product_sales").fetchall() == [(7,)]

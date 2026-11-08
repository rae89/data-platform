import dagster as dg
import duckdb
from dagster_duckdb import DuckDBResource

from data_platform.defs.ingest import raw_customers, raw_orders


def row_count(result, key):
    return result.asset_materializations_for_node(key)[0].metadata["dagster/row_count"].value


def test_ingest_seeds_history_then_appends(tmp_path):
    db = str(tmp_path / "warehouse.duckdb")
    resources = {"duckdb": DuckDBResource(database=db)}

    with dg.instance_for_test() as instance:
        first = dg.materialize([raw_customers, raw_orders], resources=resources, instance=instance)
        second = dg.materialize([raw_orders], resources=resources, instance=instance)

    assert row_count(first, "raw__customers") == 500
    assert row_count(first, "raw__orders") == 5000
    assert row_count(second, "raw__orders") == 5200

    with duckdb.connect(db, read_only=True) as conn:
        ids, distinct_ids, bad_customers = conn.execute(
            """
            select count(*), count(distinct id),
                   count(*) filter (where customer_id not between 1 and 500)
            from raw.orders
            """
        ).fetchone()
        statuses = {r[0] for r in conn.execute("select distinct status from raw.orders").fetchall()}
    # Appended batches continue the id sequence, and every order has a real customer.
    assert ids == distinct_ids == 5200
    assert bad_customers == 0
    assert statuses <= {"placed", "shipped", "completed", "returned"}

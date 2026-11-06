"""Raw ingestion into DuckDB.

These generate synthetic data so the platform runs end to end with no external
sources. Replace the SQL with real extracts (APIs, files, databases) later.
Asset keys match the dbt source `raw`, so dbt models depend on them.
"""

import dagster as dg
from dagster_duckdb import DuckDBResource


@dg.asset(key=["raw", "customers"], group_name="ingest", kinds={"duckdb"})
def raw_customers(duckdb: DuckDBResource) -> dg.MaterializeResult:
    with duckdb.get_connection() as conn:
        conn.execute("create schema if not exists raw")
        conn.execute(
            """
            create or replace table raw.customers as
            select
                i as id,
                'Customer ' || i as name,
                'Customer' || i || '@Example.com' as email,
                now() - to_days(cast(random() * 365 as integer)) as created_at
            from range(1, 501) t(i)
            """
        )
        rows = conn.execute("select count(*) from raw.customers").fetchone()[0]
    return dg.MaterializeResult(metadata={"dagster/row_count": rows})


@dg.asset(key=["raw", "orders"], group_name="ingest", kinds={"duckdb"})
def raw_orders(context: dg.AssetExecutionContext, duckdb: DuckDBResource) -> dg.MaterializeResult:
    """Seeds 90 days of history on first run, then appends a new batch each run."""
    with duckdb.get_connection() as conn:
        conn.execute("create schema if not exists raw")
        conn.execute(
            """
            create table if not exists raw.orders (
                id bigint, customer_id bigint, status varchar,
                amount_cents bigint, ordered_at timestamp
            )
            """
        )
        existing = conn.execute("select count(*) from raw.orders").fetchone()[0]
        new_rows, window_minutes = (5000, 90 * 24 * 60) if existing == 0 else (200, 60)
        conn.execute(
            """
            insert into raw.orders
            select
                (select coalesce(max(id), 0) from raw.orders) + i as id,
                1 + cast(floor(random() * 500) as bigint) as customer_id,
                list_element(['placed', 'shipped', 'completed', 'returned'],
                             1 + cast(floor(random() * 4) as integer)) as status,
                500 + cast(floor(random() * 20000) as bigint) as amount_cents,
                now()::timestamp - to_minutes(cast(random() * ? as integer)) as ordered_at
            from range(1, ? + 1) t(i)
            """,
            [window_minutes, new_rows],
        )
        rows = conn.execute("select count(*) from raw.orders").fetchone()[0]
    context.log.info(f"Inserted {new_rows} orders ({rows} total)")
    return dg.MaterializeResult(metadata={"dagster/row_count": rows})

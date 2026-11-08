"""Read-only copy of the marts for BI tools (Superset).

DuckDB allows one writer process, and a BI query holding the warehouse open would
make the next run fail. So BI tools never open the warehouse: this asset copies the
marts into a separate file after each build and swaps it in atomically. A query that
is still reading the old file keeps its copy; new queries see the new one.

It runs as its own run (eager automation), not inside refresh_all: dagster-dbt keeps
dbt's DuckDB connection open in the run process, and DuckDB won't open the same file
again in that process. A separate run also means a snapshot failure never fails the
pipeline run.
"""

import os
from pathlib import Path

import dagster as dg
from dagster_duckdb import DuckDBResource

from data_platform.defs.resources import DUCKDB_PATH

BI_DUCKDB_PATH = Path(DUCKDB_PATH).with_name("bi.duckdb")
# Lineage only: the asset copies every table in the marts schema (see below).
MARTS = [["marts", "customer_orders"], ["marts", "daily_revenue"]]


@dg.asset(
    key=["bi", "marts_snapshot"],
    group_name="serve",
    kinds={"duckdb"},
    deps=MARTS,
    # Wait for the marts' dbt tests: never publish data that failed them.
    automation_condition=(
        dg.AutomationCondition.eager() & dg.AutomationCondition.all_deps_blocking_checks_passed()
    ),
)
def bi_marts_snapshot(duckdb: DuckDBResource) -> dg.MaterializeResult:
    tmp = BI_DUCKDB_PATH.with_name(BI_DUCKDB_PATH.name + ".tmp")
    # A crashed run can leave the tmp file and its WAL; a stale WAL would be replayed.
    for leftover in (tmp, tmp.with_name(tmp.name + ".wal")):
        leftover.unlink(missing_ok=True)
    tmp_sql = str(tmp).replace("'", "''")
    with duckdb.get_connection() as conn:
        conn.execute(f"attach '{tmp_sql}' as bi")
        conn.execute("create schema bi.marts")
        tables = [
            r[0]
            for r in conn.execute(
                "select table_name from information_schema.tables"
                " where table_catalog = current_database() and table_schema = 'marts'"
                " order by 1"
            ).fetchall()
        ]
        rows = 0
        for table in tables:
            conn.execute(f'create table bi.marts."{table}" as from marts."{table}"')
            rows += conn.execute(f'select count(*) from bi.marts."{table}"').fetchone()[0]
        conn.execute("detach bi")
    os.replace(tmp, BI_DUCKDB_PATH)  # atomic: readers never see a half-written file
    # Not dagster/row_count: the SLI sensors would export it and count every mart row twice.
    return dg.MaterializeResult(
        metadata={
            "tables": len(tables),
            "rows_copied": rows,
            "path": dg.MetadataValue.path(str(BI_DUCKDB_PATH)),
        }
    )


# Dagster's built-in automation sensor starts stopped; this one runs by default and
# only launches the serve group.
serve_automation = dg.AutomationConditionSensorDefinition(
    "serve_automation",
    target=dg.AssetSelection.groups("serve"),
    default_status=dg.DefaultSensorStatus.RUNNING,
)

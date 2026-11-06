import os
from pathlib import Path

import dagster as dg
from dagster_duckdb import DuckDBResource

# Defaults to <repo>/data/warehouse.duckdb. Exported as an absolute path because the
# dbt component runs dbt from a copy of the project, where profiles.yml's relative
# default would point at the wrong place. dbt inherits this from the run process.
DUCKDB_PATH = os.environ.setdefault(
    "DUCKDB_PATH", str(Path(__file__).parents[3] / "data" / "warehouse.duckdb")
)


@dg.definitions
def resources() -> dg.Definitions:
    return dg.Definitions(
        resources={"duckdb": DuckDBResource(database=DUCKDB_PATH)},
        # DuckDB allows one writer process at a time, so run each job's steps in one process.
        executor=dg.in_process_executor,
    )

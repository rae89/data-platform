"""Reusable dlt ingestion into the DuckDB warehouse.

Each data source is one folder under defs/sources/ with two files, created by
`uv run dg scaffold defs data_platform.components.DltWarehouseLoads sources/<name>`:

- loads.py: a dlt source (any dlt source, often `rest_api_source`) and
  `pipeline = warehouse_pipeline("<name>")`.
- defs.yaml: points this component at them.

Every source lands in its own warehouse schema named after the source, and each dlt
resource becomes the Dagster asset `<source>/<resource>`, which is also the key
dagster-dbt gives the dbt source table `<source>.<resource>`. So dbt models on top of
the loaded tables are wired into the lineage with no extra code.

Keep one warehouse table per resource (`source.max_table_nesting = 0`): dlt would
otherwise split nested lists into child tables (`orders__items`) that have no asset of
their own. Unnest JSON columns in dbt staging instead.
"""

from pathlib import Path

import dagster as dg
import dlt
from dagster.components.component_scaffolding import scaffold_component
import dagster_dlt  # module import: keeps the base class out of `dg list components`

from data_platform.defs.resources import DUCKDB_PATH

LOADS_TEMPLATE = '''"""dlt source for {name}, loaded into the warehouse schema `{name}`."""

from dlt.sources.rest_api import rest_api_source

from data_platform.components import warehouse_pipeline

# One dlt resource per table. See https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api
source = rest_api_source(
    {{
        "client": {{"base_url": "https://api.example.com/v1/"}},
        "resources": ["items"],
    }},
    name="{name}",
)
source.max_table_nesting = 0  # one table per resource; unnest JSON columns in dbt

pipeline = warehouse_pipeline("{name}")
'''


def warehouse_pipeline(source_name: str) -> dlt.Pipeline:
    """A dlt pipeline that loads into the DuckDB warehouse, schema `source_name`.

    Pipeline state lives next to the warehouse (data/.dlt), so incremental cursors
    survive restarts; dlt also restores them from the warehouse if that folder is lost.
    """
    return dlt.pipeline(
        pipeline_name=source_name,
        destination=dlt.destinations.duckdb(DUCKDB_PATH),
        dataset_name=source_name,
        pipelines_dir=str(Path(DUCKDB_PATH).parent / ".dlt"),
    )


class DltWarehouseLoadsScaffolder(dg.Scaffolder):
    """Writes defs.yaml and a loads.py template for a new source."""

    def scaffold(self, request: dg.ScaffoldRequest) -> None:
        scaffold_component(
            request, {"loads": [{"source": ".loads.source", "pipeline": ".loads.pipeline"}]}
        )
        name = request.target_path.name
        (request.target_path / "loads.py").write_text(LOADS_TEMPLATE.format(name=name))


@dg.scaffold_with(DltWarehouseLoadsScaffolder)
class DltWarehouseLoads(dagster_dlt.DltLoadCollectionComponent):
    """dlt loads into the warehouse, with this platform's conventions.

    - Asset key `<source>/<resource>` in the `sources` group (loaded daily by the
      ingest_sources job), matching dbt sources.
    - No placeholder upstream assets (dagster-dlt adds one per resource by default).
    - Records `dagster/row_count`, which the SLI sensors export.
    """

    def get_asset_spec(self, data) -> dg.AssetSpec:
        spec = super().get_asset_spec(data)
        return spec.replace_attributes(
            key=dg.AssetKey([data.resource.source_name, data.resource.name]),
            deps=[],
            group_name="sources",
        )

    def execute(self, context: dg.AssetExecutionContext, dlt_pipeline_resource):
        events = dlt_pipeline_resource.run(context=context)
        # dagster-dlt's .fetch_row_count() raises when an incremental resource loaded no
        # new rows (no load job), failing the run. Count the table directly instead; one
        # table per resource makes its name the resource name.
        pipeline = getattr(events, "_dlt_pipeline", None)  # no public accessor in dagster-dlt
        for event in events:
            count = _row_count(context, pipeline, event.asset_key.path[-1]) if pipeline else None
            if count is not None:
                try:
                    event = event._replace(metadata={**(event.metadata or {}), "dagster/row_count": count})
                except AttributeError:  # observability must never break a run
                    context.log.warning("Could not attach row count: unexpected dagster-dlt event")
            yield event


def _row_count(context, pipeline: dlt.Pipeline, resource: str) -> int | None:
    """Rows in the resource's table, or None (logged) if it can't be counted."""
    try:
        with pipeline.sql_client() as client:
            # dlt normalizes names (e.g. "dailyPorts" -> "daily_ports").
            name = pipeline.default_schema.naming.normalize_table_identifier(resource)
            table = client.make_qualified_table_name(name)
            with client.execute_query(f"select count(*) from {table}") as cursor:
                return cursor.fetchone()[0]
    except Exception as e:  # observability must never break a run
        context.log.warning(f"Could not count rows for {resource}: {e}")
        return None

import importlib.util
import sys
from pathlib import Path

import dagster as dg
import duckdb
from dagster.components.testing import create_defs_folder_sandbox

from data_platform.components import DltWarehouseLoads, warehouse_pipeline

LOCAL_SOURCE = '''
import dlt

@dlt.resource(name="items", primary_key="id", write_disposition="merge")
def items(cursor=dlt.sources.incremental("id")):
    yield from [{{"id": 1, "tags": ["a", "b"]}}, {{"id": 2, "tags": []}}]

@dlt.source(name="demo")
def demo():
    return items

source = demo()
source.max_table_nesting = 0
pipeline = dlt.pipeline(
    pipeline_name="demo",
    destination=dlt.destinations.duckdb(r"{db}"),
    dataset_name="demo",
    pipelines_dir=r"{state}",
)
'''


def test_new_source_scaffolds_and_loads_into_duckdb(tmp_path):
    db = tmp_path / "warehouse.duckdb"
    with create_defs_folder_sandbox(project_name="my_project") as sandbox:
        defs_path = sandbox.scaffold_component(component_cls=DltWarehouseLoads)
        template = (defs_path / "loads.py").read_text()
        assert f'name="{defs_path.name}"' in template and "warehouse_pipeline(" in template
        compile(template, "loads.py", "exec")  # the template is valid Python

        code = LOCAL_SOURCE.format(db=db, state=tmp_path / ".dlt")
        (defs_path / "loads.py").write_text(code)
        # Load everything once outside Dagster (fresh source object), so the Dagster run
        # below finds no new rows: dlt then creates no load job for `items`, which made
        # dagster-dlt's fetch_row_count() fail the run.
        (tmp_path / "preload_demo.py").write_text(code)
        spec = importlib.util.spec_from_file_location("preload_demo", tmp_path / "preload_demo.py")
        preload = importlib.util.module_from_spec(spec)
        sys.modules["preload_demo"] = preload  # dlt looks up the defining module
        spec.loader.exec_module(preload)
        preload.pipeline.run(preload.source)
        with sandbox.load_component_and_build_defs(defs_path=defs_path) as (component, defs):
            assert isinstance(component, DltWarehouseLoads)
            spec = next(iter(defs.resolve_all_asset_specs()))
            assert spec.key == dg.AssetKey(["demo", "items"])  # matches dbt source demo.items
            assert spec.group_name == "sources" and not spec.deps  # loaded by the daily job

            with dg.instance_for_test() as instance:
                result = dg.materialize(
                    list(defs.assets), instance=instance, resources=defs.resources or {}
                )
            event = result.get_asset_materialization_events()[0]
            meta = event.event_specific_data.materialization.metadata
            assert meta["dagster/row_count"].value == 2  # exported by the SLI sensors

    with duckdb.connect(str(db), read_only=True) as conn:
        tables = {r[0] for r in conn.execute(
            "select table_name from information_schema.tables where table_schema = 'demo'"
        ).fetchall()}
    assert "items" in tables and "items__tags" not in tables  # one table per resource


def test_warehouse_pipeline_targets_the_warehouse(tmp_path, monkeypatch):
    from data_platform.components import dlt_warehouse

    # dlt creates the pipeline's state folder on creation: keep it out of the real data/.
    monkeypatch.setattr(dlt_warehouse, "DUCKDB_PATH", str(tmp_path / "warehouse.duckdb"))
    pipeline = warehouse_pipeline("some_source")
    assert pipeline.dataset_name == "some_source"
    assert Path(pipeline.pipelines_dir) == tmp_path / ".dlt"
    assert pipeline.destination.destination_type.endswith("duckdb")


def test_row_count_failure_is_logged_not_raised(tmp_path):
    import dlt

    from data_platform.components.dlt_warehouse import _row_count

    pipeline = dlt.pipeline(
        "empty", destination=dlt.destinations.duckdb(str(tmp_path / "e.duckdb")),
        dataset_name="empty", pipelines_dir=str(tmp_path / ".dlt"),
    )
    logged = []
    context = type("Ctx", (), {"log": type("Log", (), {"warning": lambda self, m: logged.append(m)})()})()
    assert _row_count(context, pipeline, "missing_table") is None
    assert "missing_table" in logged[0]

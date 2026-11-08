import re
from pathlib import Path

import duckdb
import yaml

SUPERSET = Path(__file__).parents[1] / "superset"


def test_superset_duckdb_matches_the_platform():
    # Superset must read files written by this project's duckdb; older versions can't.
    pin = re.search(r"duckdb==([\d.]+)", (SUPERSET / "Dockerfile").read_text()).group(1)
    assert pin == duckdb.__version__


def test_superset_reads_only_the_bi_snapshot():
    db = yaml.safe_load((SUPERSET / "assets" / "databases" / "warehouse.yaml").read_text())
    # Never the warehouse: an open BI query would block Dagster's writes.
    assert db["sqlalchemy_uri"] == "duckdb:////data/bi.duckdb?access_mode=read_only"
    assert not any(db[k] for k in ("allow_dml", "allow_ctas", "allow_cvas", "allow_file_upload"))


def load_assets(kind):
    return [yaml.safe_load(p.read_text()) for p in sorted((SUPERSET / "assets" / kind).rglob("*.yaml"))]


def test_dashboard_bundle_references_resolve():
    # Superset matches layout slots to charts by uuid on import. Without it, a fresh
    # instance shows the charts twice and out of place.
    db_uuids = {d["uuid"] for d in load_assets("databases")}
    datasets = {d["uuid"] for d in load_assets("datasets")}
    charts = {c["uuid"]: c for c in load_assets("charts")}
    assert all(d["database_uuid"] in db_uuids for d in load_assets("datasets"))
    assert all(c["dataset_uuid"] in datasets for c in charts.values())
    placed = []
    for dash in load_assets("dashboards"):
        slots = [v["meta"] for v in dash["position"].values() if isinstance(v, dict) and v.get("type") == "CHART"]
        assert all(m.get("uuid") in charts for m in slots), dash["dashboard_title"]
        assert all(m["sliceName"] == charts[m["uuid"]]["slice_name"] for m in slots)
        placed += [m["uuid"] for m in slots]
    assert sorted(placed) == sorted(charts)  # every chart is on exactly one dashboard

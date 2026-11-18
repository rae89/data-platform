import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
SCALE = {"s": 1, "m": 60, "h": 3600}


def stale_after_seconds():
    rules = yaml.safe_load((ROOT / "vmalert" / "rules.yml").read_text())
    alert = next(r for g in rules["groups"] for r in g["rules"] if r.get("alert") == "AssetStale")
    hours = re.fullmatch(r"sli:asset_staleness_seconds > (\d+) \* 3600", alert["expr"]).group(1)
    return int(hours) * 3600


def age_panels():
    for path in sorted((ROOT / "grafana" / "dashboards").glob("*.json")):
        for panel in json.loads(path.read_text())["panels"]:
            exprs = " ".join(t["expr"] for t in panel.get("targets", []))
            if "dagster_asset_age_seconds" in exprs or "dagster_asset_last_materialized" in exprs:
                yield path.name, panel, exprs


def test_freshness_panels_turn_red_at_the_asset_stale_slo():
    # Assets load daily; coloring against anything shorter than the alert shows
    # healthy assets as stale for most of the day.
    slo = stale_after_seconds()
    checked = 0
    for name, panel, exprs in age_panels():
        defaults = panel["fieldConfig"]["defaults"]
        if defaults["unit"] == "percentunit":
            assert f"> bool {slo // 3600} * 3600)" in exprs, (name, panel["title"])
        else:
            red = next(s["value"] for s in defaults["thresholds"]["steps"] if s["color"] == "red")
            assert red * SCALE[defaults["unit"]] == slo, (name, panel["title"])
        checked += 1
    assert checked == 8

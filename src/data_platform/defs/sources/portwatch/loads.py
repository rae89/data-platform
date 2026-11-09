"""IMF PortWatch daily port activity, loaded into the warehouse schema `portwatch`.

PortWatch (https://portwatch.imf.org) estimates daily port calls and import/export
volumes per port from ship tracking (AIS) data, broken down by ship type (container,
dry bulk, tanker, ...). It's published through a public ArcGIS API with no key, about
9 days behind real time, starting 2019-01-01.

Two daily tables, both since 2019-01-01 (see the dataset descriptions on ArcGIS):
- `daily_ports`: ship calls and import/export volumes (metric tons) per port in PORTS.
- `daily_chokepoints`: ship transits and transit volumes (metric tons) through all
  28 chokepoints PortWatch tracks (Panama Canal, Suez Canal, Strait of Hormuz, ...).

Each run fetches days after the newest one already loaded, minus a lookback window
in case recent days are revised, and merges on (portid, date).
"""

from datetime import date, timedelta

import dlt
from dlt.sources.helpers import requests  # requests with retries

from data_platform.components import warehouse_pipeline

API = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
PORTS_URL = f"{API}/Daily_Ports_Data/FeatureServer/0/query"
CHOKEPOINTS_URL = f"{API}/Daily_Chokepoints_Data/FeatureServer/0/query"
# PortWatch port ids (find more via the API's `portname` field). Each port keeps its
# own cursor, so a newly added port backfills from START on its next run.
PORTS = {"port664": "Los Angeles-Long Beach"}
START = "2019-01-01"
LOOKBACK_DAYS = 14
PAGE_SIZE = 1000  # the API's maximum


def _since(newest: str) -> str:
    return max(START, (date.fromisoformat(newest) - timedelta(days=LOOKBACK_DAYS)).isoformat())


def _fetch(url: str, where: str):
    """Yields pages of rows matching `where`, following ArcGIS paging."""
    offset = 0
    while True:
        response = requests.get(
            url,
            params={
                "where": where,
                "outFields": "*",
                "orderByFields": "date, portid",  # unique, so offset paging never skips rows
                "resultOffset": offset,
                "resultRecordCount": PAGE_SIZE,
                "returnGeometry": "false",
                "f": "json",
            },
            timeout=60,
        )
        body = response.json()
        if "error" in body:  # ArcGIS reports errors with HTTP 200
            raise RuntimeError(f"PortWatch API error: {body['error']}")
        rows = [{k: v for k, v in f["attributes"].items() if k != "ObjectId"} for f in body["features"]]
        if rows:
            yield rows
        if not body.get("exceededTransferLimit"):
            return
        offset += len(rows)


@dlt.resource(name="daily_ports", primary_key=["portid", "date"], write_disposition="merge")
def daily_ports(ports: dict[str, str] = PORTS):
    state = dlt.current.resource_state()
    newest_by_port = state.setdefault("newest_by_port", {})
    legacy = state.pop("newest_date", None)  # single cursor from before per-port cursors
    for port in ports:
        newest = newest_by_port.get(port) or legacy or START
        for rows in _fetch(PORTS_URL, f"portid = '{port}' AND date >= '{_since(newest)}'"):
            newest = max(newest, *(r["date"] for r in rows))
            yield rows
        newest_by_port[port] = newest


@dlt.resource(name="daily_chokepoints", primary_key=["portid", "date"], write_disposition="merge")
def daily_chokepoints():
    state = dlt.current.resource_state()
    newest = state.get("newest_date", START)
    for rows in _fetch(CHOKEPOINTS_URL, f"date >= '{_since(newest)}'"):
        newest = max(newest, *(r["date"] for r in rows))
        yield rows
    state["newest_date"] = newest


@dlt.source(name="portwatch")
def portwatch():
    return daily_ports, daily_chokepoints


source = portwatch()
source.max_table_nesting = 0  # one table per resource

pipeline = warehouse_pipeline("portwatch")

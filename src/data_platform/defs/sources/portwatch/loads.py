"""IMF PortWatch daily port activity, loaded into the warehouse schema `portwatch`.

PortWatch (https://portwatch.imf.org) estimates daily port calls and import/export
volumes per port from ship tracking (AIS) data, broken down by ship type (container,
dry bulk, tanker, ...). It's published through a public ArcGIS API with no key, about
9 days behind real time, starting 2019-01-01.

Each run fetches days after the newest one already loaded, minus a lookback window
in case recent days are revised, and merges on (portid, date).
"""

from datetime import date, timedelta

import dlt
from dlt.sources.helpers import requests  # requests with retries

from data_platform.components import warehouse_pipeline

URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/"
    "Daily_Ports_Data/FeatureServer/0/query"
)
# PortWatch port ids (find more via the API's `portname` field). Each port keeps its
# own cursor, so a newly added port backfills from START on its next run.
PORTS = {"port664": "Los Angeles-Long Beach"}
START = "2019-01-01"
LOOKBACK_DAYS = 14
PAGE_SIZE = 1000  # the API's maximum


def _fetch_port(port: str, since: str):
    """Yields pages of daily rows for one port from `since` on, following ArcGIS paging."""
    offset = 0
    while True:
        response = requests.get(
            URL,
            params={
                "where": f"portid = '{port}' AND date >= '{since}'",
                "outFields": "*",
                "orderByFields": "date",
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
        since = max(START, (date.fromisoformat(newest) - timedelta(days=LOOKBACK_DAYS)).isoformat())
        for rows in _fetch_port(port, since):
            newest = max(newest, *(r["date"] for r in rows))
            yield rows
        newest_by_port[port] = newest


@dlt.source(name="portwatch")
def portwatch():
    return daily_ports


source = portwatch()
source.max_table_nesting = 0  # one table per resource

pipeline = warehouse_pipeline("portwatch")

import dagster as dg

# The daily pipeline: dlt loads (group `source`), dbt staging (`transform`) and marts
# (`metrics`). bi/marts_snapshot (`serve`) runs after it on its own (defs/bi.py).
# Daily fits sources that publish daily (IMF PortWatch).
ingest_sources = dg.define_asset_job(
    "ingest_sources", selection=dg.AssetSelection.groups("source", "transform", "metrics")
)

ingest_sources_daily = dg.ScheduleDefinition(
    job=ingest_sources,
    cron_schedule="30 6 * * *",  # 06:30 UTC
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

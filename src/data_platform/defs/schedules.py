import dagster as dg

# dlt sources (defs/sources/) and the dbt models on them. bi/marts_snapshot (group
# `serve`) runs after them on its own (defs/bi.py). Daily fits sources that publish
# daily (IMF PortWatch); change the cron if a faster source is added.
ingest_sources = dg.define_asset_job("ingest_sources", selection=dg.AssetSelection.groups("sources"))

ingest_sources_daily = dg.ScheduleDefinition(
    job=ingest_sources,
    cron_schedule="30 6 * * *",  # 06:30 UTC
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

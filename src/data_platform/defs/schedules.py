import dagster as dg

SERVE = dg.AssetSelection.groups("serve")  # runs on its own after the marts (defs/bi.py)
SOURCES = dg.AssetSelection.groups("sources")  # dlt sources and the dbt models on them

# The internal pipeline, hourly. External sources run in their own job, so an API
# outage never fails this one.
refresh_all = dg.define_asset_job(
    "refresh_all", selection=dg.AssetSelection.all() - SERVE - SOURCES
)

refresh_all_hourly = dg.ScheduleDefinition(
    job=refresh_all,
    cron_schedule="0 * * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

# dlt sources (defs/sources/) and their dbt models. Daily fits sources that publish
# daily (IMF PortWatch); change the cron if a faster source is added.
ingest_sources = dg.define_asset_job("ingest_sources", selection=SOURCES)

ingest_sources_daily = dg.ScheduleDefinition(
    job=ingest_sources,
    # 06:30 UTC: off the hour, so it never starts together with refresh_all (one DuckDB writer).
    cron_schedule="30 6 * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

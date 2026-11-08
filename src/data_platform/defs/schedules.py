import dagster as dg

# Everything except the serve group, whose assets run on their own after the marts
# update (see defs/bi.py).
refresh_all = dg.define_asset_job(
    "refresh_all", selection=dg.AssetSelection.all() - dg.AssetSelection.groups("serve")
)

refresh_all_hourly = dg.ScheduleDefinition(
    job=refresh_all,
    cron_schedule="0 * * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

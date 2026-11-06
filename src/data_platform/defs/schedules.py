import dagster as dg

refresh_all = dg.define_asset_job("refresh_all", selection="*")

refresh_all_hourly = dg.ScheduleDefinition(
    job=refresh_all,
    cron_schedule="0 * * * *",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

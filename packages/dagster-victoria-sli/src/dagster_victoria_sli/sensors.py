"""Sensors that read SLIs from Dagster's own records and push them to VictoriaMetrics.

Assets don't report metrics themselves: they record materializations, row counts
and check results in Dagster as usual, and these sensors export that state.
Every metric also carries the pusher's labels (env, code_location).

After each finished run:
  dagster_run_success{job}                                       1 or 0
  dagster_run_duration_seconds{job,status}                       wall time

Every `interval_seconds`, for every asset in the code location:
  dagster_asset_materialized{asset,group}                        1 if it has ever been materialized, else 0
  dagster_asset_age_seconds{asset,group}                         seconds since its last materialization
  dagster_asset_last_materialized_timestamp_seconds{asset,group} when that was (unix time)
  dagster_asset_row_count{asset,group}                           rows at its last materialization
  dagster_asset_check_passed{asset,check}                        1 or 0 per check (dbt tests)
"""

import time

import dagster as dg

from dagster_victoria_sli.metrics import MetricsPusher


def build_sli_sensors(pusher: MetricsPusher, interval_seconds: int = 60) -> list:
    def push_run_result(context: dg.RunStatusSensorContext, succeeded: bool) -> None:
        run = context.dagster_run
        labels = {"job": run.job_name}
        samples = [("dagster_run_success", labels, 1 if succeeded else 0)]
        record = context.instance.get_run_record_by_id(run.run_id)
        if record and record.start_time and record.end_time:
            status = "success" if succeeded else "failure"
            duration = record.end_time - record.start_time
            samples.append(("dagster_run_duration_seconds", {**labels, "status": status}, duration))
        pusher.push(samples)

    @dg.run_status_sensor(
        run_status=dg.DagsterRunStatus.SUCCESS, default_status=dg.DefaultSensorStatus.RUNNING
    )
    def run_success_sli(context: dg.RunStatusSensorContext):
        push_run_result(context, succeeded=True)

    @dg.run_status_sensor(
        run_status=dg.DagsterRunStatus.FAILURE, default_status=dg.DefaultSensorStatus.RUNNING
    )
    def run_failure_sli(context: dg.RunStatusSensorContext):
        push_run_result(context, succeeded=False)

    @dg.sensor(minimum_interval_seconds=interval_seconds, default_status=dg.DefaultSensorStatus.RUNNING)
    def asset_sli(context: dg.SensorEvaluationContext):
        graph = context.repository_def.asset_graph
        keys = list(graph.get_all_asset_keys())
        entries = {
            record.asset_entry.asset_key: record.asset_entry
            for record in context.instance.get_asset_records(keys)
        }
        now = time.time()
        samples = []

        for key in keys:
            labels = {"asset": key.to_user_string(), "group": graph.get(key).group_name}
            entry = entries.get(key)
            # External assets are observed rather than materialized.
            event = entry and (entry.last_materialization or entry.last_observation)
            samples.append(("dagster_asset_materialized", labels, int(event is not None)))
            if event is None:
                continue
            samples.append(("dagster_asset_age_seconds", labels, round(now - event.timestamp, 3)))
            samples.append(("dagster_asset_last_materialized_timestamp_seconds", labels, event.timestamp))
            materialization = entry.last_materialization
            row_count = materialization and materialization.asset_materialization.metadata.get(
                "dagster/row_count"
            )
            if row_count is not None:
                samples.append(("dagster_asset_row_count", labels, row_count.value))

        checks = context.instance.event_log_storage.get_latest_asset_check_execution_by_key(
            list(graph.asset_check_keys)
        )
        for key, record in checks.items():
            if record.status.value in ("SUCCEEDED", "FAILED"):
                labels = {"asset": key.asset_key.to_user_string(), "check": key.name}
                passed = int(record.status.value == "SUCCEEDED")
                samples.append(("dagster_asset_check_passed", labels, passed))

        pusher.push(samples)
        return dg.SkipReason(f"Pushed {len(samples)} SLI samples for {len(keys)} assets")

    return [run_success_sli, run_failure_sli, asset_sli]

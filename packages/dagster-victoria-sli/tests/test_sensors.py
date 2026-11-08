import dagster as dg

from dagster_victoria_sli import MetricsPusher, build_sli_sensors


@dg.asset(group_name="ingest")
def fresh_asset() -> dg.MaterializeResult:
    return dg.MaterializeResult(metadata={"dagster/row_count": 42})


@dg.asset(group_name="ingest")
def never_run_asset() -> None: ...


class RecordingPusher(MetricsPusher):
    def push(self, samples):
        object.__getattribute__(self, "pushed").extend(samples)
        return True


def make_pusher():
    pusher = RecordingPusher(url="http://unused", labels={"env": "test"})
    object.__setattr__(pusher, "pushed", [])
    return pusher


def test_asset_sli_reports_age_for_every_asset():
    pusher = make_pusher()
    sensors = {s.name: s for s in build_sli_sensors(pusher)}
    defs = dg.Definitions(assets=[fresh_asset, never_run_asset], sensors=list(sensors.values()))

    with dg.instance_for_test() as instance:
        dg.materialize([fresh_asset], instance=instance)
        context = dg.build_sensor_context(instance=instance, repository_def=defs.get_repository_def())
        sensors["asset_sli"](context)

    by_metric = {(name, labels["asset"]): (labels, value) for name, labels, value in pusher.pushed}

    labels, materialized = by_metric[("dagster_asset_materialized", "fresh_asset")]
    assert materialized == 1 and labels["group"] == "ingest"
    assert 0 <= by_metric[("dagster_asset_age_seconds", "fresh_asset")][1] < 60
    assert by_metric[("dagster_asset_row_count", "fresh_asset")][1] == 42

    # Assets that never ran are reported, but have no age.
    assert by_metric[("dagster_asset_materialized", "never_run_asset")][1] == 0
    assert ("dagster_asset_age_seconds", "never_run_asset") not in by_metric


@dg.asset(group_name="quality")
def checked_asset() -> None: ...


@dg.asset_check(asset=checked_asset)
def passing_check() -> dg.AssetCheckResult:
    return dg.AssetCheckResult(passed=True)


@dg.asset_check(asset=checked_asset)
def failing_check() -> dg.AssetCheckResult:
    return dg.AssetCheckResult(passed=False)



observable = dg.AssetSpec("observable", group_name="external")  # external asset


def test_asset_sli_reports_checks_and_observations():
    pusher = make_pusher()
    sensors = {s.name: s for s in build_sli_sensors(pusher)}
    defs = dg.Definitions(
        assets=[checked_asset, observable], asset_checks=[passing_check, failing_check]
    )

    with dg.instance_for_test() as instance:
        dg.materialize([checked_asset, passing_check, failing_check], instance=instance)
        instance.report_runless_asset_event(dg.AssetObservation(asset_key="observable"))
        context = dg.build_sensor_context(instance=instance, repository_def=defs.get_repository_def())
        sensors["asset_sli"](context)

    checks = {
        labels["check"]: value
        for name, labels, value in pusher.pushed
        if name == "dagster_asset_check_passed"
    }
    assert checks == {"passing_check": 1, "failing_check": 0}

    by_metric = {(name, labels["asset"]): value for name, labels, value in pusher.pushed}
    # Observed (not materialized) assets get an age but no row count.
    assert by_metric[("dagster_asset_materialized", "observable")] == 1
    assert ("dagster_asset_age_seconds", "observable") in by_metric
    assert ("dagster_asset_row_count", "observable") not in by_metric
    # Materialized without a row count: no row count sample.
    assert ("dagster_asset_row_count", "checked_asset") not in by_metric


@dg.asset
def ok_asset() -> None: ...


@dg.asset
def broken_asset() -> None:
    raise ValueError("boom")


def run_sensor_samples(asset, status, sensor_name):
    pusher = make_pusher()
    sensors = {s.name: s for s in build_sli_sensors(pusher)}
    with dg.instance_for_test() as instance:
        result = dg.materialize([asset], instance=instance, raise_on_error=False)
        run = instance.get_run_by_id(result.run_id)
        event = next(e for e in result.all_events if e.event_type_value == status)
        context = dg.build_run_status_sensor_context(
            sensor_name=sensor_name, dagster_event=event, dagster_instance=instance, dagster_run=run
        )
        sensors[sensor_name](context)
    return {name: (labels, value) for name, labels, value in pusher.pushed}


def test_run_success_sli_reports_success_and_duration():
    samples = run_sensor_samples(ok_asset, "PIPELINE_SUCCESS", "run_success_sli")
    labels, value = samples["dagster_run_success"]
    assert value == 1 and labels["job"] == "__ephemeral_asset_job__"
    labels, duration = samples["dagster_run_duration_seconds"]
    assert labels["status"] == "success" and duration >= 0


def test_run_failure_sli_reports_failure():
    samples = run_sensor_samples(broken_asset, "PIPELINE_FAILURE", "run_failure_sli")
    assert samples["dagster_run_success"][1] == 0
    assert samples["dagster_run_duration_seconds"][0]["status"] == "failure"


def test_pusher_adds_common_labels():
    pusher = MetricsPusher(url="http://unused", labels={"env": "prod", "code_location": "loc"})
    line = pusher.format([("m", {"asset": 'a"b'}, 1)], timestamp=1)
    assert line == 'm{asset="a\\"b",code_location="loc",env="prod"} 1 1000'


def test_scaffolded_component_loads(monkeypatch):
    from dagster.components.testing import create_defs_folder_sandbox

    from dagster_victoria_sli import SliSensorsComponent

    monkeypatch.delenv("VICTORIA_METRICS_URL", raising=False)
    with create_defs_folder_sandbox(project_name="my_project") as sandbox:
        defs_path = sandbox.scaffold_component(component_cls=SliSensorsComponent)
        yaml_text = (defs_path / "defs.yaml").read_text()
        assert "{{ env.VICTORIA_METRICS_URL }}" in yaml_text
        assert "interval_seconds: 60" in yaml_text

        with sandbox.load_component_and_build_defs(defs_path=defs_path) as (component, defs):
            assert isinstance(component, SliSensorsComponent)
            assert component.victoria_metrics_url is None  # unset env var resolves to None
            assert sorted(s.name for s in defs.sensors) == [
                "asset_sli",
                "run_failure_sli",
                "run_success_sli",
            ]


def test_run_sli_skips_duration_without_timing(monkeypatch):
    pusher = make_pusher()
    sensors = {s.name: s for s in build_sli_sensors(pusher)}
    with dg.instance_for_test() as instance:
        result = dg.materialize([ok_asset], instance=instance)
        run = instance.get_run_by_id(result.run_id)
        event = next(e for e in result.all_events if e.event_type_value == "PIPELINE_SUCCESS")
        monkeypatch.setattr(instance, "get_run_record_by_id", lambda run_id: None)
        context = dg.build_run_status_sensor_context(
            sensor_name="run_success_sli", dagster_event=event, dagster_instance=instance, dagster_run=run
        )
        sensors["run_success_sli"](context)
    assert [name for name, _, _ in pusher.pushed] == ["dagster_run_success"]


@dg.asset_check(asset=checked_asset)
def crashing_check() -> dg.AssetCheckResult:
    raise RuntimeError("check crashed")


def test_crashed_check_is_not_reported_as_passing():
    # Its latest record stays PLANNED; the run failure SLI covers it (see TODO.md).
    pusher = make_pusher()
    sensors = {s.name: s for s in build_sli_sensors(pusher)}
    defs = dg.Definitions(assets=[checked_asset], asset_checks=[crashing_check])
    with dg.instance_for_test() as instance:
        dg.materialize([checked_asset, crashing_check], instance=instance, raise_on_error=False)
        context = dg.build_sensor_context(instance=instance, repository_def=defs.get_repository_def())
        sensors["asset_sli"](context)
    assert not [s for s in pusher.pushed if s[0] == "dagster_asset_check_passed"]

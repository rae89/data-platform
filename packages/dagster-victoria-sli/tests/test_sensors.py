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

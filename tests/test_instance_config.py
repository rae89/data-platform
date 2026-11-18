import logging
import time
from pathlib import Path
from types import SimpleNamespace

import dagster as dg
import pytest
import yaml
from dagster._core.launcher import DefaultRunLauncher
from dagster._core.storage.dagster_run import DagsterRunStatus
from dagster._core.test_utils import create_run_for_test
from dagster._daemon.monitoring import run_monitoring

ROOT = Path(__file__).parents[1]
DOCKER = yaml.safe_load((ROOT / "docker" / "dagster.yaml").read_text())
LOCAL = yaml.safe_load((ROOT / "dagster_home" / "dagster.yaml").read_text())


def test_docker_and_local_instance_config_match():
    # docker/dagster.yaml adds only storage paths for the container.
    shared = {k: v for k, v in DOCKER.items() if k in LOCAL}
    assert shared == LOCAL
    assert set(DOCKER) - set(LOCAL) == {"storage", "local_artifact_storage", "compute_logs"}


@pytest.fixture
def instance(tmp_path):
    (tmp_path / "dagster.yaml").write_text(yaml.safe_dump({"run_monitoring": LOCAL["run_monitoring"]}))
    with dg.DagsterInstance.from_config(str(tmp_path)) as instance:
        yield instance


def test_run_monitoring_settings_load_with_the_default_launcher(instance):
    # `dg dev` launches runs with the default launcher: no health checks, no resume.
    assert isinstance(instance.run_launcher, DefaultRunLauncher)
    assert not instance.run_launcher.supports_check_run_worker_health
    assert instance.run_monitoring_enabled
    assert instance.run_monitoring_max_resume_run_attempts == 0
    assert instance.run_monitoring_max_runtime_seconds == 3600


def monitor(instance, now):
    context = SimpleNamespace(instance=instance, create_request_context=lambda: None)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(run_monitoring, "get_current_timestamp", lambda: now)
        list(run_monitoring.execute_run_monitoring_iteration(context, logging.getLogger()))


def test_run_left_started_by_a_dead_worker_is_marked_failed(instance):
    # A spot interruption kills the run worker; the run stays STARTED with no process.
    run = create_run_for_test(instance, job_name="ingest_sources", status=DagsterRunStatus.NOT_STARTED)
    instance.handle_run_event(
        run.run_id,
        dg.DagsterEvent(event_type_value="PIPELINE_START", job_name=run.job_name),
    )
    assert instance.get_run_by_id(run.run_id).status == DagsterRunStatus.STARTED

    monitor(instance, time.time() + 60)  # within max_runtime_seconds: left alone
    assert instance.get_run_by_id(run.run_id).status == DagsterRunStatus.STARTED

    monitor(instance, time.time() + 3601)
    assert instance.get_run_by_id(run.run_id).status == DagsterRunStatus.FAILURE


def test_run_stuck_starting_is_marked_failed(instance):
    run = create_run_for_test(instance, job_name="ingest_sources", status=DagsterRunStatus.NOT_STARTED)
    monitor(instance, time.time() + 301)
    assert instance.get_run_by_id(run.run_id).status == DagsterRunStatus.FAILURE

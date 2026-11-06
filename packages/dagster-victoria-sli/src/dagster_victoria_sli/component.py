import os

import dagster as dg
from dagster.components.component_scaffolding import scaffold_component

from dagster_victoria_sli.metrics import MetricsPusher
from dagster_victoria_sli.sensors import build_sli_sensors

DEFAULT_VICTORIA_METRICS_URL = "http://localhost:8428"


class SliSensorsScaffolder(dg.Scaffolder):
    """Writes a defs.yaml with the usual settings for `dg scaffold defs`."""

    def scaffold(self, request: dg.ScaffoldRequest) -> None:
        scaffold_component(
            request,
            {
                "victoria_metrics_url": "{{ env.VICTORIA_METRICS_URL }}",
                "interval_seconds": 60,
            },
        )


@dg.scaffold_with(SliSensorsScaffolder)
class SliSensorsComponent(dg.Component, dg.Model, dg.Resolvable):
    """Exports run and asset SLIs from this code location to VictoriaMetrics.

    Adds three sensors: run_success_sli and run_failure_sli (one sample per
    finished run) and asset_sli (age, row count and check results for every
    asset, every `interval_seconds`).
    """

    victoria_metrics_url: str | None = None
    """VictoriaMetrics base URL. Falls back to $VICTORIA_METRICS_URL, then http://localhost:8428."""

    interval_seconds: int = 60
    """How often asset_sli runs."""

    environment: str | None = None
    """`env` label on every metric. Falls back to $PLATFORM_ENV, then "local"."""

    code_location: str | None = None
    """`code_location` label on every metric. Defaults to the project folder name."""

    def build_defs(self, context: dg.ComponentLoadContext) -> dg.Definitions:
        pusher = MetricsPusher(
            url=self.victoria_metrics_url
            or os.getenv("VICTORIA_METRICS_URL")
            or DEFAULT_VICTORIA_METRICS_URL,
            labels={
                "env": self.environment or os.getenv("PLATFORM_ENV", "local"),
                "code_location": self.code_location or context.project_root.name,
            },
        )
        return dg.Definitions(sensors=build_sli_sensors(pusher, self.interval_seconds))

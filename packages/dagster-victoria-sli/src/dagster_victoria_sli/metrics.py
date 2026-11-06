"""Push metrics to VictoriaMetrics using its Prometheus text import API."""

import logging
import time
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

Sample = tuple[str, dict[str, str], float]


def _escape(value) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


@dataclass(frozen=True)
class MetricsPusher:
    """Sends (name, labels, value) samples to VictoriaMetrics.

    `labels` are added to every sample (e.g. env, code_location). Pushing never
    raises: a monitoring outage must not fail a sensor or a pipeline.
    """

    url: str
    labels: dict[str, str] = field(default_factory=dict)
    timeout: float = 5.0

    def format(self, samples: list[Sample], timestamp: float | None = None) -> str:
        ts_ms = int((timestamp or time.time()) * 1000)
        lines = []
        for name, labels, value in samples:
            merged = {**self.labels, **labels}
            label_str = ",".join(f'{k}="{_escape(v)}"' for k, v in sorted(merged.items()))
            lines.append(f"{name}{{{label_str}}} {value} {ts_ms}")
        return "\n".join(lines)

    def push(self, samples: list[Sample]) -> bool:
        if not samples:
            return True
        try:
            resp = requests.post(
                f"{self.url.rstrip('/')}/api/v1/import/prometheus",
                data=self.format(samples).encode(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            log.warning("Could not push metrics to VictoriaMetrics: %s", e)
            return False

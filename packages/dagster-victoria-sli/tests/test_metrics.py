import logging

import requests

from dagster_victoria_sli import MetricsPusher
from dagster_victoria_sli import metrics


class FakeResponse:
    def __init__(self, status):
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status} error")


def test_push_posts_prometheus_text(monkeypatch):
    calls = []
    monkeypatch.setattr(
        metrics.requests,
        "post",
        lambda url, data, timeout: calls.append((url, data, timeout)) or FakeResponse(204),
    )
    pusher = MetricsPusher(url="http://vm:8428/", labels={"env": "test"}, timeout=2)

    assert pusher.push([("m", {"job": "j"}, 1)]) is True
    url, data, timeout = calls[0]
    assert url == "http://vm:8428/api/v1/import/prometheus"
    assert data.decode().startswith('m{env="test",job="j"} 1 ')
    assert timeout == 2


def test_push_with_no_samples_sends_nothing(monkeypatch):
    monkeypatch.setattr(metrics.requests, "post", lambda *a, **k: 1 / 0)
    assert MetricsPusher(url="http://vm").push([]) is True


def test_push_failures_are_logged_not_raised(monkeypatch, caplog):
    pusher = MetricsPusher(url="http://vm")

    monkeypatch.setattr(metrics.requests, "post", lambda *a, **k: FakeResponse(500))
    with caplog.at_level(logging.WARNING):
        assert pusher.push([("m", {}, 1)]) is False

    def down(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(metrics.requests, "post", down)
    assert pusher.push([("m", {}, 1)]) is False
    assert "Could not push metrics" in caplog.text


def test_format_keeps_epoch_timestamp_and_escapes_labels():
    line = MetricsPusher(url="http://vm").format([("m", {"a": "x\\y\nz"}, 2.5)], timestamp=0)
    assert line == 'm{a="x\\\\y\\nz"} 2.5 0'

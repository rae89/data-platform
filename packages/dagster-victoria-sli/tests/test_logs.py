import collections
import logging
import time

import dagster as dg
import pytest
import requests

from dagster_victoria_sli import logs
from dagster_victoria_sli.logs import STREAM_FIELDS, VictoriaLogsHandler, _Sender


@pytest.fixture
def sent(monkeypatch):
    """Captures batches instead of posting them, and isolates the shared senders."""
    batches = []
    monkeypatch.setattr(_Sender, "_send", lambda self, batch: batches.append(batch))
    monkeypatch.setattr(logs, "_senders", {})
    return batches


def wait_for(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while not predicate():
        assert time.time() < deadline, "timed out"
        time.sleep(0.01)


def make_record(msg="hello", level=logging.INFO, **extra):
    record = logging.LogRecord("dagster", level, __file__, 1, msg, None, None)
    record.__dict__.update(extra)
    return record


def test_entry_uses_dagster_metadata(monkeypatch, sent):
    monkeypatch.setenv("PLATFORM_ENV", "prod")
    handler = VictoriaLogsHandler(url="http://vl:9428/")
    event = type("Event", (), {"event_type_value": "STEP_START"})()
    record = make_record(
        "job - run - step - raw text",
        dagster_meta={
            "orig_message": "raw text",
            "job_name": "refresh_all",
            "run_id": "r1",
            "step_key": "s1",
            "dagster_event": event,
        },
    )
    entry = handler._to_entry(record)

    assert handler.endpoint == "http://vl:9428/insert/jsonline"
    assert entry["_msg"] == "raw text"
    assert entry["env"] == "prod"
    assert entry["level"] == "info"
    assert (entry["job"], entry["run_id"], entry["step_key"], entry["event_type"]) == (
        "refresh_all",
        "r1",
        "s1",
        "STEP_START",
    )
    assert "exception" not in entry


def test_entry_without_dagster_metadata_includes_exception(sent):
    handler = VictoriaLogsHandler(url="http://vl")
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = make_record("plain", logging.ERROR, exc_info=sys.exc_info())
    entry = handler._to_entry(record)

    assert entry["_msg"] == "plain"
    assert entry["job"] == entry["run_id"] == entry["event_type"] == ""
    assert "ValueError: boom" in entry["exception"]


def test_emit_batches_and_flushes(sent):
    handler = VictoriaLogsHandler(url="http://vl", batch_size=2, flush_interval=0.01)
    for i in range(3):
        handler.emit(make_record(f"m{i}"))
    wait_for(lambda: sum(len(b) for b in sent) == 3)

    assert [len(b) for b in sent] == [2, 1]
    assert [e["_msg"] for b in sent for e in b] == ["m0", "m1", "m2"]


def test_close_flushes_queued_entries_and_stops(sent):
    sender = _Sender("http://vl/insert/jsonline", batch_size=100, flush_interval=60)
    sender.put({"_msg": "last"})
    sender.close()

    assert not sender._thread.is_alive()
    assert sent == [[{"_msg": "last"}]]
    sender.close()  # second close is a no-op


def test_full_queue_drops_instead_of_blocking(sent):
    sender = _Sender("http://vl", batch_size=1, flush_interval=60)
    sender.close()  # stop the consumer so the queue fills
    sender._queue.maxsize = 1
    sender.put({"_msg": "kept"})
    sender.put({"_msg": "dropped"})
    assert sender._queue.qsize() == 1


def test_emit_reports_formatting_errors(monkeypatch, sent):
    handler = VictoriaLogsHandler(url="http://vl")
    errors = []
    monkeypatch.setattr(handler, "_to_entry", lambda r: 1 / 0)
    monkeypatch.setattr(handler, "handleError", errors.append)
    record = make_record()
    handler.emit(record)
    assert errors == [record]


def test_handlers_with_same_settings_share_a_sender(sent):
    a = VictoriaLogsHandler(url="http://vl")
    b = VictoriaLogsHandler(url="http://vl/")
    c = VictoriaLogsHandler(url="http://other")
    assert a._sender is b._sender
    assert a._sender is not c._sender


def test_send_posts_jsonlines_and_swallows_errors(monkeypatch):
    sender = _Sender("http://vl/insert/jsonline", batch_size=1, flush_interval=60)
    sender.close()
    calls = []

    def post(url, params, data, timeout):
        calls.append((url, params, data))
        raise requests.ConnectionError("down")

    monkeypatch.setattr(sender._session, "post", post)
    sender._send([{"a": 1}, {"b": "x"}])  # must not raise

    assert calls == [
        ("http://vl/insert/jsonline", {"_stream_fields": STREAM_FIELDS}, b'{"a": 1}\n{"b": "x"}')
    ]


@dg.asset
def tiny_asset():
    return 1


def test_run_logs_are_not_lost_when_dagster_rebuilds_handlers(sent):
    """Dagster closes handlers whenever it builds a new log manager. Events logged
    through an older log manager afterwards (RUN_SUCCESS) must still be shipped."""
    config = {
        "python_logs": {
            "dagster_handler_config": {
                "handlers": {
                    "vl": {
                        "class": "dagster_victoria_sli.logs.VictoriaLogsHandler",
                        "level": "DEBUG",
                        "url": "http://vl",
                        "flush_interval": 0.01,
                    }
                }
            }
        }
    }
    with dg.instance_for_test(overrides=config) as instance:
        result = dg.materialize([tiny_asset], instance=instance)

    expected = collections.Counter(e.event_type_value for e in result.all_events)

    def shipped():
        entries = [e for b in sent for e in b if e["run_id"] == result.run_id and e["event_type"]]
        return collections.Counter(e["event_type"] for e in entries)

    wait_for(lambda: shipped() == expected)
    assert expected["PIPELINE_SUCCESS"] == 1

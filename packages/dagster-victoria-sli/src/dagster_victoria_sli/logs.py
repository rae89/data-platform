"""Logging handler that ships Dagster logs to VictoriaLogs.

Records are queued and sent in batches from a background thread, so logging
never blocks or fails a run. Configure it in the instance's dagster.yaml:

    python_logs:
      dagster_handler_config:
        handlers:
          victorialogs:
            class: dagster_victoria_sli.logs.VictoriaLogsHandler
            level: DEBUG

The URL and env label default to $VICTORIA_LOGS_URL and $PLATFORM_ENV.
"""

import atexit
import json
import logging
import os
import queue
import threading
from datetime import datetime, timezone

import requests


# Fields VictoriaLogs uses to group log lines into streams. Keep these low-cardinality.
STREAM_FIELDS = "service,env,job"


class VictoriaLogsHandler(logging.Handler):
    def __init__(
        self,
        url: str | None = None,
        service: str = "dagster",
        environment: str | None = None,
        batch_size: int = 200,
        flush_interval: float = 1.0,
        level: int = logging.NOTSET,
    ):
        super().__init__(level)
        url = url or os.getenv("VICTORIA_LOGS_URL", "http://localhost:9428")
        self.endpoint = f"{url.rstrip('/')}/insert/jsonline"
        self.service = service
        self.environment = environment or os.getenv("PLATFORM_ENV", "local")
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue: queue.Queue[dict | None] = queue.Queue(maxsize=10_000)
        self._session = requests.Session()
        self._thread = threading.Thread(target=self._run, name="victorialogs", daemon=True)
        self._thread.start()
        atexit.register(self.close)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._queue.put_nowait(self._to_entry(record))
        except queue.Full:
            pass  # Drop rather than block the pipeline.
        except Exception:
            self.handleError(record)

    def _to_entry(self, record: logging.LogRecord) -> dict:
        meta = getattr(record, "dagster_meta", None) or {}
        event = meta.get("dagster_event")
        entry = {
            "_time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            # Dagster's raw message, without its "job - run_id - step - " prefix.
            "_msg": meta.get("orig_message") or record.getMessage(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "service": self.service,
            "env": self.environment,
            "job": meta.get("job_name") or "",
            "run_id": meta.get("run_id") or "",
            "step_key": meta.get("step_key") or "",
            "event_type": event.event_type_value if event is not None else "",
        }
        if record.exc_info:
            entry["exception"] = logging.Formatter().formatException(record.exc_info)
        return entry

    def _run(self) -> None:
        stop = False
        while not stop:
            batch: list[dict] = []
            try:
                item = self._queue.get(timeout=self.flush_interval)
                while True:
                    if item is None:
                        stop = True
                        break
                    batch.append(item)
                    if len(batch) >= self.batch_size:
                        break
                    item = self._queue.get_nowait()
            except queue.Empty:
                pass
            if batch:
                self._send(batch)

    def _send(self, batch: list[dict]) -> None:
        body = "\n".join(json.dumps(e, default=str) for e in batch)
        try:
            self._session.post(
                self.endpoint,
                params={"_stream_fields": STREAM_FIELDS},
                data=body.encode(),
                timeout=5,
            )
        except requests.RequestException:
            pass  # VictoriaLogs being down must not affect runs.

    def close(self) -> None:
        if self._thread.is_alive():
            self._queue.put(None)
            self._thread.join(timeout=5)
        super().close()

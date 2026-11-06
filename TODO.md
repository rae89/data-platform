# TODO

## Add tracing with VictoriaTraces

One trace per Dagster run, with each asset/step as a span and each dbt model as a
child span. Use the run's `run_id` as the trace ID (both are 128-bit), so traces
line up with the `run_id` already on every VictoriaLogs line and with the Dagster
run page.

- [ ] Add a `victoriatraces` service to `docker-compose.yml`. Check the current
      VictoriaTraces docs for the image tag, port and OTLP/Jaeger endpoint paths.
- [ ] Add a trace-export sensor to `packages/dagster-victoria-sli`, next to the SLI
      sensors. After each run, read the run's events (run/step start and end,
      materializations, check results) plus dbt's per-model timings, and send spans
      over OTLP with the real start and end times. No changes to assets needed.
- [ ] Configure the endpoint with a `VICTORIA_TRACES_URL` env var, like
      `VICTORIA_METRICS_URL` and `VICTORIA_LOGS_URL`. Tag spans with `env`.
- [ ] Add a Jaeger data source in `grafana/provisioning/datasources` pointing at
      VictoriaTraces.
- [ ] Link logs and traces in Grafana: `run_id` on a log line opens the trace, and a
      span opens its logs filtered by `run_id`.
- [ ] Later, once ingestion pulls from real sources: add live OpenTelemetry spans in
      `defs/ingest.py` (auto-instrument `requests` and DB drivers) to see individual
      API calls and retries.

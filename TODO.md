# TODO

## Send alerts somewhere

vmalert evaluates the SLO alerts, but `-notifier.blackhole` discards them, so a
broken pipeline goes unnoticed until someone opens Grafana.

- [ ] Add an Alertmanager service to `docker-compose.yml` with a config that routes
      to Slack or email.
- [ ] Point vmalert at it: replace `-notifier.blackhole` with `-notifier.url`.
- [ ] Add Alertmanager as a Grafana data source so alerts and silences show there.

## Add a `just ci` recipe and linting

There's no CI config yet. One command should run every check, as the safety net
before adding a remote.

- [ ] Add `ruff` to the dev dependencies and configure it in `pyproject.toml`.
- [ ] Add a `ci` recipe that runs `just --fmt --check`, `dg check defs`, `pytest`,
      a dbt parse, and `ruff`.

## Add project-level tests

The top-level `tests/` folder is empty.

- [ ] Add a smoke test that materializes every asset against a temporary DuckDB
      file, to catch broken SQL and dbt/Dagster wiring.

## Fix stale comment in `_sources.yml`

- [ ] `dbt_project/models/staging/_sources.yml` says ingest lives in
      `src/data_platform/assets/ingest.py`. It's actually in
      `src/data_platform/defs/ingest.py`.

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

## Rewrite existing docs in the PRs-and-docs style

`AGENTS.md` now asks for outcome-first docs, but `README.md` and the package README
predate the rule.

- [ ] Rewrite `README.md` so the first lines say what the platform does and how to
      start it, following "Writing PRs and docs" in `AGENTS.md`.
- [ ] Do the same for `packages/dagster-victoria-sli/README.md`.

## Report crashed asset checks as failing

A check that raises an exception keeps a `PLANNED` record, and `asset_sli` only
exports `SUCCEEDED` and `FAILED`, so the check drops off the dashboard instead of
showing as failing. The run failure SLI still fires.

- [ ] In `packages/dagster-victoria-sli/src/dagster_victoria_sli/sensors.py`, export
      `PLANNED` checks whose run has finished as failed (`dagster_asset_check_passed 0`).
- [ ] Update `test_crashed_check_is_not_reported_as_passing` to expect 0.

## Align revenue definitions across marts

`daily_revenue` excludes returned orders, but `customer_orders.lifetime_value`
includes them, so the Superset "Sales overview" totals don't add up (the table is
labelled "incl. returns" for now).

- [ ] Decide whether lifetime value should exclude returns, and change
      `dbt_project/models/marts/customer_orders.sql` to match `daily_revenue`.
- [ ] Rename the Superset chart back and re-export `superset/assets/`.

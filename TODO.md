# TODO

## Finish the AWS deploy (`infra/`)

`tofu apply` creates the host, but the repo is deployed by hand and an
interrupted spot instance can leave Dagster in a bad state.

- [ ] Enable `run_monitoring` in `docker/dagster.yaml`, so a run killed by a spot
      interruption is marked failed instead of staying "STARTED".
- [ ] Check what comes back after `aws ec2 stop-instances` / `start-instances`; switch
      services on `restart: on-failure:3` to `unless-stopped` if they stay down.
- [ ] Automate steps 4 and 5 of `infra/README.md` (clone with a read-only deploy key
      from SSM, write `.env` from SSM, `just up`).
- [ ] Move OpenTofu state to an S3 backend.
- [ ] Back up `data/` and the Docker volumes (EBS snapshots via Data Lifecycle Manager).
- [ ] Check that `tofu destroy` cancels the persistent spot request.

## Deploy `infra/` from GitHub Actions

`tofu apply` runs from a laptop, so changes skip review and nobody sees the plan.
Start with plain GitHub Actions; switch to Digger (OpenTaco, open source, runs in
Actions) for plan comments on PRs or more stacks. Skip Atlantis: it needs inbound
webhooks. Needs the S3 backend above. About 1 to 2 hours.

- [ ] Add a GitHub OIDC provider and a deploy role in `infra/`, limited to this repo,
      so CI holds no AWS keys.
- [ ] Add `.github/workflows/infra.yml`: `tofu fmt -check`, `validate` and `plan` on
      PRs that touch `infra/`; `apply` on merge to `main`.
- [ ] Put `apply` behind a GitHub Environment with a required reviewer.
- [ ] Document the flow in `infra/README.md`.

## Demo access: self-approved read-only visitors, Cloudflare Access as the only login

To show the platform to customers or hiring managers without handing out passwords:
visitors sign in with an emailed one-time code and get read-only access; you keep full
access with Google. Today anyone let in gets Dagster run controls, Grafana Admin and
the VictoriaMetrics delete API. About 6 to 8 hours; needs the domain (`infra/README.md`).

- [ ] Add a one-time-PIN identity provider and a demo Access application in
      `infra/public.tf`: any verified email (or emails ending in listed domains), 4-hour
      sessions, only the portal, Superset, Grafana and a read-only Dagster. Keep the
      writable Dagster and the Victoria UIs and APIs admin-only (`allowed_emails`).
- [ ] Run a second Dagster web server with `--read-only` for the demo hostname.
- [ ] Grafana: `[auth.jwt]` on the `Cf-Access-Jwt-Assertion` header, checked against
      `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`; admin emails get
      Admin, everyone else Viewer; turn off the login form and anonymous access; set
      `root_url`. Only via env on the server, so `just up` locally stays as it is.
- [ ] Superset: check the same signed token in `superset_config.py` (not the plain
      email header, which anyone reaching the server directly can fake), create users
      on first visit; admin emails get Admin, everyone else a dashboards-only role with
      no SQL Lab (DuckDB can read any file in the container). Add tests.
- [ ] Keep a local admin login as a backup for SSM port forwarding and Tailscale,
      which bypass Cloudflare and carry no token.

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
- [ ] Add live OpenTelemetry spans in the dlt sources (`defs/sources/*/loads.py`,
      auto-instrument `requests`) to see individual
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


## Daily freshness thresholds in Grafana

Every asset loads daily (alert `AssetStale`, 26h), but the Grafana
"Asset age" panel and the freshness heatmap still color everything against 2h, so
assets show as stale most of the day.

- [ ] In `grafana/dashboards/data-platform-slis.json` and
      `dagster-asset-freshness.json`, use a 26h threshold.

## Port filter on "Trade trends" before adding a second port

`port_monthly_trade` stores year-over-year change per port, and the "Change vs. a year
earlier" chart shows `MAX` of it, which is only right for one port. Sums and cargo per
call already aggregate correctly.

- [ ] When a second port is added to `PORTS` in `sources/portwatch/loads.py`, add a port
      filter to the "Trade trends" dashboard and re-export `superset/assets/`.

## Retake the README screenshots

The Dagster, Grafana and VictoriaLogs screenshots show `refresh_all`, the synthetic-data
job that was removed; the portal one shows its widget.

- [ ] Run `ingest_sources`, then retake `docs/screenshots/{portal,dagster-run,grafana-sli-dashboard,victorialogs-run-logs}.png`
      and update their captions in `README.md`.

## dlt dashboard: browse table rows with DuckDB 2.0

`just dlt-dashboard` shows pipelines, schema, state and loads, but browsing table
rows fails: dlt 1.32 calls DuckDB's `fetch_arrow_table()`, removed in DuckDB 2.0
(dlt's `duckdb` extra still caps duckdb below 2.0).

- [ ] When a dlt release supports DuckDB 2.0, upgrade dlt and check the dashboard's
      data browser and "Load row counts".

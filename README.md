# Data platform

dbt + Dagster + DuckDB, with SLI metrics in VictoriaMetrics and logs in VictoriaLogs.

![Architecture: Dagster runs ingest and dbt into DuckDB; SLI sensors and the log handler feed VictoriaMetrics and VictoriaLogs, which vmalert and Grafana read; the Homepage portal links and health-checks every service, shows live SLIs from VictoriaMetrics and pulls update feeds from GitHub](docs/architecture.svg)

The diagram is drawn with d3 by `docs/diagram/architecture.mjs`. After editing it,
run `just diagram` (needs Node) and commit the regenerated `docs/architecture.svg`.

## Quick start

Commands are [`just`](https://github.com/casey/just) recipes (`brew install just`,
or `uv tool install rust-just`). Run `just` to list them.

```bash
just up
```

Start at the portal: one landing page linking every component, with status and live SLIs.

| Service          | URL                    |
|------------------|------------------------|
| **Portal**       | http://localhost:3002  (landing page) |
| Dagster          | http://localhost:3000  |
| Grafana          | http://localhost:3001  (opens the "Data Platform SLIs" dashboard) |
| VictoriaMetrics  | http://localhost:8428/vmui |
| VictoriaLogs     | http://localhost:9428/select/vmui |
| vmalert          | http://localhost:8880  |

The `refresh_all` job runs every hour. To run it now, open Dagster, go to
Jobs → refresh_all → Materialize all.

For local development with hot reload, run `just dev` (`dg dev`). It runs Dagster
on your machine against the same Victoria stack and the same DuckDB file.

## Screenshots

The portal landing page: every component with its status, live SLIs, the last Dagster run, recent platform changes and upstream releases.

![Portal landing page with tiles for Dagster, Grafana, VictoriaMetrics, VictoriaLogs and vmalert, status dots and live SLI values](docs/screenshots/portal.png)

A `refresh_all` run in Dagster: every step succeeded and all dbt tests passed as asset checks.

![Dagster run page for refresh_all showing a successful run and passing dbt asset checks](docs/screenshots/dagster-run.png)

The SLI dashboard in Grafana, after the SLI sensors exported that run.

![Grafana Data Platform SLIs dashboard with run success rate, check pass rate, asset age, run duration, row count and logs](docs/screenshots/grafana-sli-dashboard.png)

The same run's logs in VictoriaLogs (`service:dagster job:refresh_all`).

![VictoriaLogs vmui showing log lines for the refresh_all run](docs/screenshots/victorialogs-run-logs.png)

## Portal

The portal (http://localhost:3002) runs [Homepage](https://gethomepage.dev). It's
built to be replaceable:

1. `portal/catalog.yaml` lists every component in a tool-neutral format: name, group,
   description, URL and health check URL. Homepage-only extras (live widgets) sit
   under a `homepage:` key.
2. `just portal` renders the catalog into `portal/homepage/services.yaml` and restarts
   the portal. Look and layout live in `portal/homepage/settings.yaml`, `bookmarks.yaml`,
   `widgets.yaml` (header) and `custom.css` (iOS-style glass cards; it targets
   Homepage's own class names, not Tailwind classes).
3. The Docker service is called `portal`, not `homepage`, so nothing else refers to
   the tool.

To add a component, add it to the catalog and run `just portal`. To replace Homepage,
write a renderer for the new tool that reads the same catalog, and swap the image in
`docker-compose.yml`.

The portal also shows update feeds, defined under `feeds:` in the catalog:

- **Platform changes:** the last 5 merged PRs in this repo. The repo is private, so
  this needs a fine-grained token with "Pull requests: Read-only" for this repo.
  Without it the tile shows an API error.
  - **With 1Password** (recommended): save the token in the Personal vault as an
    item named `data-platform-github-token` with the token in its `credential` field,
    then run `just up`. `.env.op` holds the reference and `op run` injects it, so the
    token is never written to disk.
  - **Without 1Password:** copy `.env.example` to `.env`, paste the token, run `just up`.
- **Upstream releases:** the latest Dagster, Grafana, VictoriaMetrics and Homepage
  releases, from their public GitHub release feeds. Compare them with the pinned
  versions in `docker-compose.yml` and `pyproject.toml` to see when to upgrade.

Homepage has one page, not a page per service. For more views, put groups on tabs
(`layout.<group>.tab` in `portal/homepage/settings.yaml`) or embed a page with
Homepage's `iframe` widget.

## Dagster project (dg)

The project was scaffolded with `create-dagster project` and is managed with the
`dg` CLI. `definitions.py` loads everything in `defs/` automatically, so new
definitions need no registration:

```bash
uv run dg scaffold defs dagster.asset my_asset.py      # new asset file in defs/
uv run dg check defs                                   # validate YAML and definitions
uv run dg list defs                                    # show assets, checks, jobs, sensors
uv run dg utils refresh-defs-state                     # re-parse dbt after model changes
```

dbt assets come from the `dagster_dbt.DbtProjectComponent` configured in
`defs/dbt/defs.yaml`. Each dbt model becomes an asset and each dbt test an asset check.

## Layout

```
dbt_project/                 dbt models (staging → marts) and tests
src/data_platform/
  definitions.py             entry point: loads everything in defs/ (scaffolded by dg)
  defs/
    dbt/defs.yaml            DbtProjectComponent: dbt models → assets, tests → checks
    ingest.py                raw.customers, raw.orders (synthetic data, replace with real sources)
    resources.py             DuckDB resource and in-process executor
    schedules.py             refresh_all job, hourly
    sli/defs.yaml            SliSensorsComponent: exports SLIs to VictoriaMetrics
packages/dagster-victoria-sli/  shared package: SliSensorsComponent and VictoriaLogsHandler
vmalert/rules.yml            SLI recording rules and SLO alerts
grafana/                     datasources and the SLI dashboard
portal/catalog.yaml          every component, for the portal landing page (`just portal`)
portal/homepage/             Homepage config; services.yaml is generated from the catalog
docs/diagram/                d3 script that renders docs/architecture.svg (`just diagram`)
docs/screenshots/            UI screenshots used in this README
dagster_home/dagster.yaml    Dagster config for `just dev`
docker/dagster.yaml          Dagster config inside Docker
```

## SLIs

| SLI | Metric | SLO (in vmalert/rules.yml) |
|-----|--------|-----|
| Pipeline success rate | `dagster_run_success{job}` (1/0 per run) | ≥ 95% over 7 days |
| Freshness | `dagster_asset_age_seconds{asset,group}` (also `..._last_materialized_timestamp_seconds`) | refreshed within 2h |
| Coverage | `dagster_asset_materialized{asset,group}` (1/0, every asset) | every asset has run |
| Data quality | `dagster_asset_check_passed{asset,check}` (dbt tests and any other checks) | all checks passing |
| Run duration | `dagster_run_duration_seconds{job,status}` | dashboard only |
| Volume | `dagster_asset_row_count{asset,group}` | dashboard only |

Assets don't push metrics themselves. They record materializations, row counts
(`dagster/row_count`) and check results in Dagster as usual. The sensors from
`SliSensorsComponent` (configured in `defs/sli/defs.yaml`) export that state every
minute and after each run. Every metric also has a `code_location` label.

The component and the VictoriaLogs handler come from the shared package
[`packages/dagster-victoria-sli`](packages/dagster-victoria-sli), a uv workspace
member of this repo. It's a separate installable package, so other code locations
can reuse it (see its README).

Asset metrics cover every asset in the code location, including ones that have
never run. The `AssetStale` alert uses the last known timestamp, so it still fires
if Dagster stops reporting, and `SliMetricsMissing` fires when reports stop arriving.

vmalert records these as `sli:*` series. Alerts appear in the vmalert UI. To get
notified, add an Alertmanager and point vmalert's `-notifier.url` at it.

Every metric and log line has an `env` label, set with `PLATFORM_ENV`.

## Querying logs

In Grafana, or at http://localhost:9428/select/vmui, using LogsQL:

```
service:dagster level:error
service:dagster run_id:"<run id>"
service:dagster job:refresh_all | stats by (event_type) count()
```

## Notes

- DuckDB allows only one process to write at a time. Jobs use the in-process
  executor for that reason. When you open the file yourself while Dagster runs,
  open it read-only: `duckdb -readonly data/warehouse.duckdb`.
- After changing dbt models, `just dev` re-parses automatically. For Docker,
  rebuild with `just up`.
- Runs started with `dg launch` execute inside the CLI process and aren't tied to
  the code location, so the run success and duration SLIs skip them. Asset SLIs
  still update. Launch from the UI or let the schedule run them to count toward
  the run SLIs.
- `dagster dev` in one container is fine for a single machine. For production,
  run the webserver and daemon separately with Postgres storage.

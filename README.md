# Data platform

dbt + Dagster + DuckDB, with SLI metrics in VictoriaMetrics and logs in VictoriaLogs.

```
Dagster ──runs──> ingest assets ──> DuckDB (data/warehouse.duckdb) <── dbt models + tests
   │
   ├─ sensors + assets push SLI metrics ──> VictoriaMetrics ──> vmalert (SLO rules)
   └─ log handler ships run logs ─────────> VictoriaLogs
                                                 └── both shown in Grafana
```

## Quick start

```bash
make up
```

| Service          | URL                    |
|------------------|------------------------|
| Dagster          | http://localhost:3000  |
| Grafana          | http://localhost:3001  (opens the "Data Platform SLIs" dashboard) |
| VictoriaMetrics  | http://localhost:8428/vmui |
| VictoriaLogs     | http://localhost:9428/select/vmui |
| vmalert          | http://localhost:8880  |

The `refresh_all` job runs every hour. To run it now, open Dagster, go to
Jobs → refresh_all → Materialize all.

For local development with hot reload, run `make dev` (`dg dev`). It runs Dagster
on your machine against the same Victoria stack and the same DuckDB file.

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
dagster_home/dagster.yaml    Dagster config for `make dev`
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
- After changing dbt models, `make dev` re-parses automatically. For Docker,
  rebuild with `make up`.
- Runs started with `dg launch` execute inside the CLI process and aren't tied to
  the code location, so the run success and duration SLIs skip them. Asset SLIs
  still update. Launch from the UI or let the schedule run them to count toward
  the run SLIs.
- `dagster dev` in one container is fine for a single machine. For production,
  run the webserver and daemon separately with Postgres storage.

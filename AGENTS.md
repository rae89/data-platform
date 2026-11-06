# AGENTS.md

Guidance for AI coding agents working in this repo. See `README.md` for the full
overview and `TODO.md` for planned work.

## What this is

A local data platform: Dagster orchestrates ingest assets and dbt models that write
to DuckDB (`data/warehouse.duckdb`). Observability runs on the Victoria stack:
SLI metrics go to VictoriaMetrics, run logs to VictoriaLogs, SLO rules run in
vmalert, and Grafana shows all of it.

## Commands

Python 3.12, managed with `uv`. Run tools through `uv run`. Project commands are
`just` recipes in `justfile` (`just --list` shows them all). If `just` isn't
installed, run recipes with `uvx --from rust-just just <recipe>`.

```bash
just up              # everything in Docker (Dagster :3000, Grafana :3001)
just infra           # only the Victoria stack + Grafana
just dev             # infra + local Dagster with hot reload (uv run dg dev)
just check           # validate definitions and component YAML (uv run dg check defs)
just defs-state      # re-parse dbt after changing models
just test            # tests (extra args go to pytest, e.g. just test -k sensor)
uv run dg list defs  # list assets, checks, jobs, sensors
```

After any change to Dagster definitions or component YAML, run `just check`.
After changing dbt models, run `just defs-state` (and `just check`).

## Layout

- `src/data_platform/defs/`: Dagster definitions, loaded automatically by
  `definitions.py`. New files need no registration.
  - `ingest.py`: raw assets (synthetic data for now). Asset keys `raw/*` match the
    dbt source `raw`.
  - `dbt/defs.yaml`: `DbtProjectComponent`. Each dbt model is an asset, each test
    an asset check.
  - `sli/defs.yaml`: `SliSensorsComponent` config.
  - `resources.py`, `schedules.py`: DuckDB resource, executor, hourly `refresh_all`.
- `dbt_project/`: dbt models (`staging` → `marts`) and tests.
- `packages/dagster-victoria-sli/`: shared, separately installable package
  (uv workspace member) with the SLI sensors component and the VictoriaLogs handler.
  Keep it free of anything specific to this code location.
- `vmalert/rules.yml`: SLI recording rules (`sli:*`) and SLO alerts.
- `grafana/`: provisioned data sources and dashboards (JSON).
- `docker/dagster.yaml` (Docker) and `dagster_home/dagster.yaml` (`just dev`): instance
  config. Keep both in sync.

## Rules and gotchas

- **DuckDB allows one writer process.** Keep the in-process executor. Don't add
  multiprocess executors or open the warehouse for writing from other processes.
  Open it read-only for inspection: `duckdb -readonly data/warehouse.duckdb`.
- **Assets don't push metrics.** They record `dagster/row_count` metadata and check
  results. The SLI sensors export that state to VictoriaMetrics. Follow this pattern
  for new assets.
- **Observability must never break a run.** Exporters and log handlers swallow
  network errors and drop data rather than block.
- Every metric and log line carries `env` (from `PLATFORM_ENV`); metrics also carry
  `code_location`. Keep label and stream-field cardinality low (no run IDs as metric
  labels).
- Configure endpoints with env vars (`VICTORIA_METRICS_URL`, `VICTORIA_LOGS_URL`)
  and default to localhost.
- If you rename or add a metric, update `vmalert/rules.yml`, the Grafana dashboards
  and the SLI table in `README.md` together.
- Don't edit generated or runtime files: `dbt_project/target/`, `dbt_project/logs/`,
  `dagster_home/` storage and history, `data/`.

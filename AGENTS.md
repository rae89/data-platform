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
just diagram         # re-render docs diagrams (docs/diagram/*.mjs → docs/*.svg)
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
- `docs/diagram/`: d3 scripts for docs diagrams. `architecture.mjs` draws the README
  diagram; if you add or remove a component, update it and run `just diagram`.
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
- **Documentation diagrams use d3.** For any diagram or flow chart in the docs
  (README, `docs/`, package READMEs, Notion pages), don't use Mermaid, ASCII art or
  image editors. This doesn't apply to Grafana dashboards or other runtime
  visuals. Add one script per diagram, `docs/diagram/<name>.mjs` (copy
  `architecture.mjs`), that writes `docs/<name>.svg`. Run `just diagram`, commit the
  script and the SVG, and embed the SVG with `![alt text](docs/<name>.svg)`. READMEs
  and Notion can't run d3, so always ship the static SVG.
- **Keep `docs/architecture.svg` current on every commit.** Before committing, check
  whether the change adds, removes or renames a component, service or data flow. If
  it does, update `docs/diagram/architecture.mjs` and run `just diagram` in the same
  commit.
- Don't edit generated or runtime files: `dbt_project/target/`, `dbt_project/logs/`,
  `dagster_home/` storage and history, `data/`, `docs/*.svg` (regenerate them instead).

## Planned work (`TODO.md`)

`TODO.md` is the backlog, in priority order. Each item is a heading with a short
reason and checkbox steps.

- Check it before starting related work, and follow the plan there unless the user
  asks for something different.
- When you finish a step, check its box. When every box under a heading is
  checked, remove the item.
- If you find follow-up work you won't do now (bugs, gaps, missing tests), add it as
  a new item rather than leaving TODO comments in code.

## Before finishing a change

- Use `just` recipes and `uv run dg ...` rather than calling `dagster` directly.
- Run `just check` and `just test`, and report any failures.
- Update `README.md`, this file and `TODO.md` if the change affects them.

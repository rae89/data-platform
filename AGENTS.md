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
just cov             # tests with coverage, fails below 99%
just dlt-dashboard   # dlt pipeline dashboard (schema, state, loads), :2718
just portal          # render the portal landing page from portal/catalog.yaml
just diagram         # re-render docs diagrams (docs/diagram/*.mjs → docs/*.svg)
uv run dg list defs  # list assets, checks, jobs, sensors
```

After any change to Dagster definitions or component YAML, run `just check`.
After changing dbt models, run `just defs-state` (and `just check`).

## Layout

- `src/data_platform/defs/`: Dagster definitions, loaded automatically by
  `definitions.py`. New files need no registration.
  - `sources/<name>/`: one dlt source per folder (`defs.yaml` + `loads.py`), using
    the `DltWarehouseLoads` component. Assets `<name>/<table>`, schema `<name>`.
  - `dbt/defs.yaml`: `DbtProjectComponent`. Each dbt model is an asset, each test
    an asset check.
  - `sli/defs.yaml`: `SliSensorsComponent` config.
  - `resources.py`, `schedules.py`: DuckDB resource, executor, daily `ingest_sources`.
  - `bi.py`: `bi/marts_snapshot`, a read-only copy of the marts (`data/bi.duckdb`)
    for Superset. Runs as its own run via the `serve_automation` sensor.
- `src/data_platform/components/`: project components (`DltWarehouseLoads`: dlt into
  the warehouse with this platform's conventions, plus its `dg scaffold` template).
- `dbt_project/`: dbt models (`staging` → `marts`) and tests.
- `packages/dagster-victoria-sli/`: shared, separately installable package
  (uv workspace member) with the SLI sensors component and the VictoriaLogs handler.
  Keep it free of anything specific to this code location.
- `vmalert/rules.yml`: SLI recording rules (`sli:*`) and SLO alerts.
- `grafana/`: provisioned data sources and dashboards (JSON).
- `superset/`: Superset image (DuckDB driver pinned to the uv.lock version), config,
  and `assets/` imported on start (the warehouse connection).
- `portal/catalog.yaml`: tool-neutral list of every component for the portal landing
  page (Homepage, :3002). `just portal` renders `portal/homepage/services.yaml`; don't
  edit that file by hand.
- `docs/diagram/`: d3 scripts for docs diagrams. `architecture.mjs` draws the README
  diagram; if you add or remove a component, update it and run `just diagram`.
- `infra/`: Terraform for AWS hosting: one EC2 spot instance, published through
  Cloudflare Access with Google sign-in (`public.tf`), no inbound ports. See
  `infra/README.md`.
- `docker/dagster.yaml` (Docker) and `dagster_home/dagster.yaml` (`just dev`): instance
  config. Keep both in sync.
- `.claude/settings.json`: Claude Code plugins for this repo (ponytail,
  i-have-adhd). Claude Code offers to install them when you trust the folder.
- `.github/pull_request_template.md`: PR description layout.

## Rules and gotchas

- **DuckDB allows one writer process.** Keep the in-process executor. Don't add
  multiprocess executors or open the warehouse for writing from other processes.
  Open it read-only for inspection: `duckdb -readonly data/warehouse.duckdb`.
  BI tools (Superset) read `data/bi.duckdb`, never the warehouse: even a read-only
  query holds a lock that makes the next run fail.
- **New data sources use dlt.** Scaffold with
  `uv run dg scaffold defs data_platform.components.DltWarehouseLoads sources/<name>`,
  keep `source.max_table_nesting = 0` (one table per resource; unnest JSON in dbt
  staging), and add dbt sources/staging under `dbt_project/models/staging/<name>/`.
  Don't install `dlt[duckdb]`: its extra caps duckdb below 2.0.
- **Asset groups follow the layers.** dlt loads are `source`, dbt staging is
  `transform`, dbt marts are `metrics` (set per folder in `dbt_project.yml`), the BI
  snapshot is `serve`. Job `ingest_sources` builds the first three daily (06:30 UTC);
  freshness alert `AssetStale` fires after 26h.
- **Assets don't push metrics.** They record `dagster/row_count` metadata and check
  results. The SLI sensors export that state to VictoriaMetrics. Follow this pattern
  for new assets.
- **Observability must never break a run.** Exporters and log handlers swallow
  network errors and drop data rather than block.
- Every metric and log line carries `env` (from `PLATFORM_ENV`); metrics also carry
  `code_location`. Keep label and stream-field cardinality low (no run IDs as metric
  labels).
- **Never commit secrets.** Add a 1Password reference to `.env.op`
  (`op://<vault>/<item>/<field>`, resolved by `op run` in `just up`), document the
  variable in `.env.example`, and read it in `docker-compose.yml` as `${NAME:-}`.
- Configure endpoints with env vars (`VICTORIA_METRICS_URL`, `VICTORIA_LOGS_URL`)
  and default to localhost.
- If you add, remove or move a service, update `portal/catalog.yaml` and run
  `just portal`, in addition to the architecture diagram. If it has a web UI, add it
  to `local.services` in `infra/public.tf` and set `public:` in the catalog.
- **Public access goes through Cloudflare Access only.** Never open inbound ports in
  `infra/main.tf`: most services have no login of their own.
- If you rename or add a metric, update `vmalert/rules.yml`, the Grafana dashboards,
  the portal widgets in `portal/catalog.yaml` and the SLI table in `README.md`
  together.
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

## Writing PRs and docs

PR descriptions, commit messages, `README.md`, `docs/` and package READMEs follow
the [i-have-adhd](https://github.com/ayghri/i-have-adhd) style, so a reader can act
after reading only the top. In Claude Code, `/i-have-adhd` applies the same rules.

- **Outcome first.** The first line says what now works or what to do. No preamble.
- **Number multi-step tasks.** One bounded action per step, fewest steps that work.
- **Show how to try it.** A command, URL or file path the reader can use right away.
- **Specific, not vague.** Concrete time estimates and numbers ("about 10 minutes",
  "6 assets"), never "some work" or "a few".
- **At most 5 items per list.** Group and rank the rest.
- **No recaps or closing lines.** End when the content ends. State errors and risks
  plainly: cause, then fix.

When creating a PR (including with `gh pr create --body`), read
`.github/pull_request_template.md` first and fill in every section.

## Before finishing a change

- Use `just` recipes and `uv run dg ...` rather than calling `dagster` directly.
- Run `just check` and `just cov`, and report any failures. Keep coverage at 99% or
  more: new code comes with tests.
- Update `README.md`, this file and `TODO.md` if the change affects them.

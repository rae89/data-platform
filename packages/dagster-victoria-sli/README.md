# dagster-victoria-sli

Shared observability for Dagster code locations:

- `SliSensorsComponent`: a `dg` component that exports run and asset SLIs to VictoriaMetrics.
- `VictoriaLogsHandler`: a logging handler that ships Dagster logs to VictoriaLogs.

## Add it to a code location

```bash
uv add dagster-victoria-sli
dg scaffold defs dagster_victoria_sli.SliSensorsComponent sli
```

This creates `defs/sli/defs.yaml`:

```yaml
type: dagster_victoria_sli.SliSensorsComponent
attributes:
  victoria_metrics_url: '{{ env.VICTORIA_METRICS_URL }}'
  interval_seconds: 60
```

| Attribute | Default | Meaning |
|-----------|---------|---------|
| `victoria_metrics_url` | `$VICTORIA_METRICS_URL`, then `http://localhost:8428` | where to push metrics |
| `interval_seconds` | `60` | how often `asset_sli` runs |
| `environment` | `$PLATFORM_ENV`, then `local` | `env` label on every metric |
| `code_location` | the project folder name | `code_location` label on every metric |

The package lives in the data-platform repo under `packages/dagster-victoria-sli`.
data-platform uses it as a uv workspace member. Until it's published to an index,
other code locations can install it from git:

```toml
# pyproject.toml of another code location
[tool.uv.sources]
dagster-victoria-sli = { git = "<data-platform repo URL>", subdirectory = "packages/dagster-victoria-sli" }
```

## Logs

The log handler runs inside each run's process, so install this package in every
code location and reference it from the instance's `dagster.yaml`:

```yaml
python_logs:
  dagster_handler_config:
    handlers:
      victorialogs:
        class: dagster_victoria_sli.logs.VictoriaLogsHandler
        level: DEBUG
```

It reads `$VICTORIA_LOGS_URL` (default `http://localhost:9428`) and `$PLATFORM_ENV`.

## Metrics

Every metric has `env` and `code_location` labels.

| Metric | Labels | Sent |
|--------|--------|------|
| `dagster_run_success` | `job` | after each run (1 or 0) |
| `dagster_run_duration_seconds` | `job`, `status` | after each run |
| `dagster_asset_materialized` | `asset`, `group` | every interval, for every asset (1 or 0) |
| `dagster_asset_age_seconds` | `asset`, `group` | every interval |
| `dagster_asset_last_materialized_timestamp_seconds` | `asset`, `group` | every interval |
| `dagster_asset_row_count` | `asset`, `group` | every interval, if the asset records `dagster/row_count` |
| `dagster_asset_check_passed` | `asset`, `check` | every interval, per completed check (1 or 0) |

Pushing never raises. If VictoriaMetrics is down, a warning is logged and that
sample is dropped.

## Development

From the data-platform root:

```bash
uv sync
uv run pytest packages/dagster-victoria-sli/tests
```

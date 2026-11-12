export DAGSTER_HOME := justfile_directory() / "dagster_home"

# List recipes
default:
    @just --list

# Start everything (Dagster, Victoria stack, Grafana) in Docker
up:
    #!/usr/bin/env sh
    # Secrets come from 1Password (.env.op) when op can resolve them, else from .env.
    # Secrets only feed optional extras, so never let a 1Password problem block startup.
    if command -v op >/dev/null 2>&1 && op run --env-file .env.op -- true >/dev/null; then
        op run --env-file .env.op -- docker compose up -d --build
    else
        echo "1Password secrets unavailable (see op error above); using .env if present"
        docker compose up -d --build
    fi

# Stop all containers (data is kept in volumes and ./data)
down:
    docker compose down

# Start only VictoriaMetrics, VictoriaLogs, vmalert and Grafana
infra:
    docker compose up -d victoriametrics victorialogs vmalert grafana

# Run Dagster locally with hot reload (stops the dagster container first)
dev: infra
    docker compose stop dagster
    uv run dg dev

# Validate component YAML and definitions
check:
    uv run dg check defs

# Run tests (extra args go to pytest)
test *args:
    uv run pytest packages/dagster-victoria-sli/tests tests {{ args }}

# Run tests with coverage; fails below 99%
cov *args:
    uv run pytest packages/dagster-victoria-sli/tests tests --cov {{ args }}

# Every check CI runs (.github/workflows/ci.yml); needs uv and OpenTofu
ci: defs-state check cov
    {{ just_executable() }} --fmt --check
    tofu -chdir=infra fmt -check
    tofu -chdir=infra init -backend=false -input=false > /dev/null
    tofu -chdir=infra validate

# Server: switch to the images CI built for main (no local build), then restart what changed
update:
    git pull --ff-only
    docker compose pull dagster superset
    docker compose up -d

# Rebuild the dbt component state (manifest) after changing dbt models
defs-state:
    uv run dg utils refresh-defs-state

# Render the portal from portal/catalog.yaml and restart it (settings and CSS need a restart)
portal:
    uv run python portal/render_homepage.py
    docker compose restart portal

# Pipelines store their warehouse path only at run time, so it's passed in, read-only
# (AGENTS.md: other processes open the warehouse read-only). `dlt dashboard` requires
# the commercial dlt[hub]; dlt's own run_dashboard() (open source) doesn't.
# dlt dashboard (http://localhost:2718): pipelines, schema, state, loads and run traces
dlt-dashboard:
    #!/usr/bin/env sh
    set -e
    db="${DUCKDB_PATH:-{{ justfile_directory() }}/data/warehouse.duckdb}"
    export DESTINATION__DUCKDB__CREDENTIALS__DATABASE="$db"
    export DESTINATION__DUCKDB__CREDENTIALS__READ_ONLY=true
    uv run --group dashboard python -c "from dlt._workspace.helpers.dashboard.runner import run_dashboard; run_dashboard(pipelines_dir='$(dirname "$db")/.dlt', port=2718)"

# Follow Dagster container logs
logs:
    docker compose logs -f dagster

# Remove containers, volumes and the local warehouse
clean:
    docker compose down -v
    rm -rf data/*.duckdb* dbt_project/target src/data_platform/defs/.local_defs_state

# Regenerate the d3 diagrams (docs/diagram/*.mjs → docs/*.svg)
diagram:
    cd docs/diagram && npm install --silent && for f in *.mjs; do node "$f"; done

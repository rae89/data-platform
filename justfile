export DAGSTER_HOME := justfile_directory() / "dagster_home"

# List recipes
default:
    @just --list

# Start everything (Dagster, Victoria stack, Grafana) in Docker
up:
    docker compose up -d --build

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

# Rebuild the dbt component state (manifest) after changing dbt models
defs-state:
    uv run dg utils refresh-defs-state

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

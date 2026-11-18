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

# Lint and check formatting of the Python code (ruff, configured in pyproject.toml)
lint:
    uv run ruff check .
    uv run ruff format --check .

# Every check CI runs (.github/workflows/ci.yml); needs uv and OpenTofu
ci: lint defs-state check cov
    {{ just_executable() }} --fmt --check
    tofu -chdir=infra fmt -check
    tofu -chdir=infra init -backend=false -input=false > /dev/null
    tofu -chdir=infra validate

# Server: switch to the images CI built for main (no local build), then restart what changed
update ref="origin/main": (update-pull ref)
    docker compose up -d

# Server: fast-forward to ref and pull the images CI built for exactly that commit
update-pull ref="origin/main":
    #!/usr/bin/env bash
    set -euo pipefail
    # The deploy job fetches before calling this; fetch only for origin/main or a missing commit.
    if [ "{{ ref }}" = origin/main ] || ! git cat-file -e "{{ ref }}^{commit}" 2>/dev/null; then
        git fetch --quiet origin main
    fi
    # Generated, and rewritten with public links on the server (portal-public): discard
    # it so the fast-forward doesn't stop on it, and render it again below.
    git checkout -- portal/homepage/services.yaml
    git merge --ff-only "{{ ref }}"
    # CI tags each image sha-<commit> (images.yml); retag it as the :main that
    # docker-compose.yml runs, so the images always match the checkout.
    tag="sha-$(git rev-parse HEAD)"
    for name in dagster superset; do
        image="ghcr.io/rae89/data-platform-$name"
        docker pull --quiet "$image:$tag"
        docker tag "$image:$tag" "$image:main"
    done
    if grep -q '^PORTAL_PUBLIC_URL=.' .env 2>/dev/null; then {{ just_executable() }} portal-public; fi

# Server: render the portal with public links (PORTAL_PUBLIC_URL in .env), in the Dagster
# image because the server has no uv
portal-public:
    #!/usr/bin/env bash
    set -euo pipefail
    url=$(sed -n 's/^PORTAL_PUBLIC_URL=//p' .env)
    [ -n "$url" ] || { echo "Set PORTAL_PUBLIC_URL in .env first"; exit 1; }
    docker compose run --rm --no-deps -e PORTAL_PUBLIC_URL="$url" -v ./portal:/portal \
        --entrypoint python dagster /portal/render_homepage.py

# Rebuild the dbt component state (manifest) after changing dbt models
defs-state:
    uv run dg utils refresh-defs-state

# Render the portal from portal/catalog.yaml and restart it (settings and CSS need a restart)
portal:
    uv run python portal/render_homepage.py
    docker compose restart portal

# Public landing page (Cloudflare Pages) into landing/dist; needs PORTAL_PUBLIC_URL
landing:
    uv run python portal/render_landing.py

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

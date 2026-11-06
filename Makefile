.PHONY: up down infra dev check defs-state logs clean

export DAGSTER_HOME := $(CURDIR)/dagster_home

up:          ## Start everything (Dagster, Victoria stack, Grafana) in Docker
	docker compose up -d --build

down:        ## Stop all containers (data is kept in volumes and ./data)
	docker compose down

infra:       ## Start only VictoriaMetrics, VictoriaLogs, vmalert and Grafana
	docker compose up -d victoriametrics victorialogs vmalert grafana

dev: infra   ## Run Dagster locally with hot reload (stops the dagster container first)
	docker compose stop dagster
	uv run dg dev

check:       ## Validate component YAML and definitions
	uv run dg check defs

defs-state:  ## Rebuild the dbt component state (manifest) after changing dbt models
	uv run dg utils refresh-defs-state

logs:        ## Follow Dagster container logs
	docker compose logs -f dagster

clean:       ## Remove containers, volumes and the local warehouse
	docker compose down -v
	rm -rf data/*.duckdb* dbt_project/target src/data_platform/defs/.local_defs_state

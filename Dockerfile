FROM python:3.12-slim

COPY --from=astral/uv:0.9.26 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

# dg names the code location after this folder, matching a local checkout (data-platform).
WORKDIR /opt/data-platform
COPY pyproject.toml uv.lock .python-version ./
# Workspace members (the shared dagster-victoria-sli package) are installed with the dependencies.
COPY packages ./packages
RUN uv sync --frozen --no-install-project

COPY src ./src
COPY dbt_project ./dbt_project
RUN uv sync --frozen

ENV VIRTUAL_ENV=/opt/data-platform/.venv \
    PATH=/opt/data-platform/.venv/bin:$PATH \
    DAGSTER_HOME=/opt/dagster/home \
    DUCKDB_PATH=/data/warehouse.duckdb

# Build the dbt component's state (manifest) into the image so the code location
# loads without parsing dbt at startup.
RUN dg utils refresh-defs-state && mkdir -p $DAGSTER_HOME /data
COPY docker/dagster.yaml $DAGSTER_HOME/dagster.yaml

EXPOSE 3000
# `dg dev` runs the webserver and daemon (schedules, sensors) in one container.
CMD ["dg", "dev", "--host", "0.0.0.0", "--port", "3000"]

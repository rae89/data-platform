# Superset with the DuckDB driver. The official image ships without database drivers.
# The -py312 variant: duckdb 2.x needs Python 3.11+, and the default 6.1.0 image has 3.10.
FROM apache/superset:6.1.0-py312

USER root
# Keep duckdb on the same version as uv.lock, so Superset can read files Dagster writes
# (tests/test_superset.py checks this).
RUN . /app/.venv/bin/activate && uv pip install duckdb==2.0.0 duckdb-engine==0.17.0

COPY --chown=superset superset_config.py /app/superset_config.py
# On PYTHONPATH (/app/pythonpath) so superset_config.py can import it.
COPY --chown=superset cf_access.py /app/pythonpath/cf_access.py
COPY --chown=superset assets /app/superset_assets
COPY --chown=superset --chmod=755 entrypoint.sh /app/entrypoint.sh
ENV SUPERSET_CONFIG_PATH=/app/superset_config.py

USER superset
CMD ["/app/entrypoint.sh"]

# Superset settings for the data platform (loaded via SUPERSET_CONFIG_PATH).
# SUPERSET_SECRET_KEY comes from the environment; Superset reads it itself.
# Metadata (users, charts, dashboards) lives in SQLite under /app/superset_home.

ROW_LIMIT = 10_000

# Trust X-Forwarded-Proto/Host from cloudflared (infra/public.tf), so redirects stay on
# https and the public hostname. Superset is only reachable through it or localhost.
ENABLE_PROXY_FIX = True

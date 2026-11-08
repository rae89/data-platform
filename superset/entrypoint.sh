#!/bin/sh
# Starts Superset: set up the metadata DB and admin user, import the warehouse
# connection from /app/superset_assets, then run the web server.
set -e

if [ -z "$SUPERSET_SECRET_KEY" ] || [ -z "$SUPERSET_ADMIN_PASSWORD" ]; then
  echo "Superset needs SUPERSET_SECRET_KEY and SUPERSET_ADMIN_PASSWORD." >&2
  echo "Run \`just up\` with 1Password set up (.env.op), or set them in .env." >&2
  exit 1
fi

superset db upgrade
# create-admin is a no-op if the user exists; reset-password keeps it in sync with the secret.
superset fab create-admin --username admin --firstname Admin --lastname User \
  --email admin@localhost --password "$SUPERSET_ADMIN_PASSWORD"
superset fab reset-password --username admin --password "$SUPERSET_ADMIN_PASSWORD"
superset init
superset import-directory --overwrite /app/superset_assets

exec /app/docker/entrypoints/run-server.sh

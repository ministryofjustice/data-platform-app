#!/usr/bin/env bash

set -euo pipefail

# Start Postgres
docker compose --file contrib/docker-compose-postgres.yml up --detach

make install

# Run migrations
uv run python manage.py migrate
apm install --frozen

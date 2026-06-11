#!/usr/bin/env bash

# Start Postgres
docker compose --file contrib/docker-compose-postgres.yml up --detach

set -euo pipefail

make install

# Run migrations
uv run python manage.py migrate

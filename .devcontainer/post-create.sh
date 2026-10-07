#!/usr/bin/env bash

set -euo pipefail

# Start Postgres
docker compose --file contrib/docker-compose-postgres.yml up --detach

make install

# Install Playwright browser and system dependencies
uv run playwright install --with-deps chromium

# Run migrations
uv run python manage.py migrate
apm install --frozen

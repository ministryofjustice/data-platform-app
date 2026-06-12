#!/usr/bin/env bash

set -euo pipefail

# Start Postgres
make db-start

# Install dependencies
make install

# Run migrations
uv run python manage.py migrate

# Synchronise Agent Package Manager
apm install --frozen

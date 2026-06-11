#!/usr/bin/env bash
set -euo pipefail

ADDRESS=${ADDRESS:-"0.0.0.0"}
PORT=${PORT:-"8000"}
WORKERS=${WORKERS:-"4"}
LOG_LEVEL=${LOG_LEVEL:-"info"}

echo "Run django checks"
python manage.py check --deploy

echo "Migrating the database"
python manage.py migrate --noinput

echo "Running Django server on ${ADDRESS}:${PORT}"
gunicorn data_platform_app.wsgi:application \
  --bind "${ADDRESS}:${PORT}" \
  --workers 2 \
  --threads 4 \
  --log-level "${LOG_LEVEL}" \
  --access-logfile - \
  --error-logfile -

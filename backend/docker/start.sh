#!/bin/sh
set -eu

export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export CELERY_BROKER_URL="${CELERY_BROKER_URL:-redis://127.0.0.1:6379/1}"
export CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-redis://127.0.0.1:6379/2}"

echo "Migrating database..."
alembic upgrade head

echo "Starting Redis, API, and Celery in one container..."
exec /usr/bin/supervisord -n -c /app/docker/supervisord.conf

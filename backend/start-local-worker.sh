#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
. .venv/bin/activate
celery -A celery_worker.celery worker --loglevel=INFO --concurrency="${CELERY_WORKER_CONCURRENCY:-4}"

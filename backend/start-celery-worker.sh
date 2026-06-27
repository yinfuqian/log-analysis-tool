#!/bin/bash
set -e

if [ -d ".venv" ]; then
  source .venv/bin/activate
elif [ -d "venv" ]; then
  source venv/bin/activate
fi

celery -A celery_worker.celery worker --loglevel=info --concurrency=4


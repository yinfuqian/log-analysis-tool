#!/bin/bash
set -e

source .venv/bin/activate
celery -A celery_worker.celery_app worker --loglevel=INFO --concurrency=4

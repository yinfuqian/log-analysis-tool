#!/usr/bin/env bash
# start-local-worker 脚本负责后端或客户端的启动、构建与运行环境准备。
set -euo pipefail

cd "$(dirname "$0")"
. .venv/bin/activate
celery -A celery_worker.celery worker --loglevel=INFO --concurrency="${CELERY_WORKER_CONCURRENCY:-4}"

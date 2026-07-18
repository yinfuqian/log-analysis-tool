#!/bin/bash
# start-celery-worker 脚本负责后端或客户端的启动、构建与运行环境准备。
set -e

if [ -d ".venv" ]; then
  source .venv/bin/activate
elif [ -d "venv" ]; then
  source venv/bin/activate
fi

celery -A celery_worker.celery worker --loglevel=info --concurrency=4


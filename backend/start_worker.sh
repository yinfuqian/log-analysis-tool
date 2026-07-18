#!/bin/bash
# start worker 脚本负责后端或客户端的启动、构建与运行环境准备。
set -e

source .venv/bin/activate
celery -A celery_worker.celery_app worker --loglevel=INFO --concurrency=4

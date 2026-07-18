#!/bin/sh
# docker-entrypoint 脚本负责后端或客户端的启动、构建与运行环境准备。
set -e

mkdir -p "${LOCAL_STORAGE_DIR:-/data/upload}" "${LOG_DIR:-/app/app/logs}" /tmp/log-analyzer-repos

exec "$@"

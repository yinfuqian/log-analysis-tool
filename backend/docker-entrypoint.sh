#!/bin/sh
# docker-entrypoint 脚本负责后端或客户端的启动、构建与运行环境准备。
set -e

# Codex CLI 不会自动创建 CODEX_HOME，容器内即使改了路径也要保证它存在。
mkdir -p "${LOCAL_STORAGE_DIR:-/data/upload}" "${LOG_DIR:-/app/app/logs}" /tmp/log-analyzer-repos \
  "${CODEX_HOME:-/data/codex}" "${SKILL_WORKSPACE_DIR:-/data/skill-workspace}"

exec "$@"

#!/usr/bin/env bash
# start-local-api 脚本负责后端或客户端的启动、构建与运行环境准备。
set -euo pipefail

cd "$(dirname "$0")"
. .venv/bin/activate
python app.py

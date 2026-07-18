#!/bin/bash
# migrate db 脚本负责后端或客户端的启动、构建与运行环境准备。
set -e

export FLASK_APP=app.py

python init_database.py

if [ ! -d "migrations" ]; then
  flask db init
fi

if ! flask db upgrade; then
  echo "flask db upgrade failed, applying idempotent bootstrap_schema.py fallback..."
  python bootstrap_schema.py
  flask db current
else
  python bootstrap_schema.py
  flask db current
fi

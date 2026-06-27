#!/bin/bash
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

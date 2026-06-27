#!/bin/sh
set -e

mkdir -p "${LOCAL_STORAGE_DIR:-/data/upload}" "${LOG_DIR:-/app/app/logs}" /tmp/log-analyzer-repos

exec "$@"

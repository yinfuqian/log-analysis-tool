# 故障分析工具后端镜像采用多阶段构建，最终运行镜像不携带测试、配置和默认用户密码文件。
ARG PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.10-slim-bookworm

FROM ${PYTHON_BASE_IMAGE} AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_APP=app.py \
    AUTH_USERS_FILE=/data/users.csv \
    PADDLE_PDX_CACHE_HOME=/data/paddle-cache \
    REPO_CACHE_DIR=/tmp/fault-analyzer-repos

WORKDIR /app

# 系统镜像源和 Python 镜像源都允许在企业网络中通过构建参数替换。
ARG APT_MIRROR=https://mirrors.aliyun.com/debian
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}|g; s|http://security.debian.org/debian-security|${APT_MIRROR}-security|g" /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}|g; s|http://security.debian.org/debian-security|${APT_MIRROR}-security|g" /etc/apt/sources.list; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS build

# 构建阶段安装完整依赖并复制源码，用于编译检查、应用检查、Worker 检查和真实 OCR 预测。
COPY requirements.txt requirements-ocr.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -i "${PIP_INDEX_URL}" -r requirements.txt \
    && python -m pip install -i "${PIP_INDEX_URL}" -r requirements-ocr.txt

COPY . .

# 使用示例用户表完成构建自检；该文件不会复制到最终运行镜像。
RUN find /app -type f -name '*.sh' -exec sed -i 's/\r$//' {} + \
    && chmod +x /app/docker-entrypoint.sh /app/migrate_db.sh /app/start.sh /app/start_worker.sh \
    && mkdir -p /data/upload /data/paddle-cache /app/app/logs /tmp/fault-analyzer-repos \
    && python -m pip check \
    && python -m compileall -q app.py celery_worker.py extensions.py app bootstrap_schema.py init_database.py manage_users.py verify_runtime.py \
    && AUTH_USERS_FILE=/app/users.example.csv python verify_runtime.py --build \
    && AUTH_USERS_FILE=/app/users.example.csv python verify_runtime.py --ocr \
    && rm -rf /app/app/logs/* \
    && find /app -type d -name '__pycache__' -prune -exec rm -rf '{}' +

FROM base AS runtime

# 最终阶段使用白名单复制运行依赖和业务文件，避免把源码仓库中的测试、环境文件和临时产物带入生产。
COPY --from=build /usr/local /usr/local
COPY --from=build /app/app /app/app
COPY --from=build /app/migrations /app/migrations
COPY --from=build /app/app.py /app/app.py
COPY --from=build /app/celery_worker.py /app/celery_worker.py
COPY --from=build /app/extensions.py /app/extensions.py
COPY --from=build /app/bootstrap_schema.py /app/bootstrap_schema.py
COPY --from=build /app/init_database.py /app/init_database.py
COPY --from=build /app/manage_users.py /app/manage_users.py
COPY --from=build /app/verify_runtime.py /app/verify_runtime.py
COPY --from=build /app/docker-entrypoint.sh /app/docker-entrypoint.sh
COPY --from=build /app/migrate_db.sh /app/migrate_db.sh
COPY --from=build /app/start.sh /app/start.sh
COPY --from=build /app/start_worker.sh /app/start_worker.sh
COPY --from=build /data/paddle-cache /data/paddle-cache

RUN chmod +x /app/docker-entrypoint.sh /app/migrate_db.sh /app/start.sh /app/start_worker.sh \
    && mkdir -p /data/upload /app/app/logs /tmp/fault-analyzer-repos

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python verify_runtime.py --runtime || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "gunicorn -w ${WEB_CONCURRENCY:-4} -k ${GUNICORN_WORKER_CLASS:-gthread} --threads ${WEB_THREADS:-8} --timeout ${GUNICORN_TIMEOUT:-300} --bind 0.0.0.0:5000 'app:create_app()'"]

# 故障分析工具后端生产镜像：构建成功代表 API、Worker、Git 和 OCR 均通过自检。
ARG PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.10-slim-bookworm
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_APP=app.py \
    AUTH_USERS_FILE=/app/users.csv \
    PADDLE_PDX_CACHE_HOME=/data/paddle-cache \
    REPO_CACHE_DIR=/tmp/fault-analyzer-repos

WORKDIR /app

# 镜像源均可通过构建参数替换，便于内网或离线镜像仓库使用。
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

# 先复制依赖文件以复用 Docker 缓存，再复制业务源码。
COPY requirements.txt requirements-ocr.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -i "${PIP_INDEX_URL}" -r requirements.txt \
    && python -m pip install -i "${PIP_INDEX_URL}" -r requirements-ocr.txt

COPY . .

# 构建期执行完整自检。OCR 模型会下载到镜像目录，并在首次挂载命名卷时自动初始化到卷中。
RUN chmod +x /app/docker-entrypoint.sh /app/migrate_db.sh /app/start.sh /app/start_worker.sh \
    && mkdir -p /data/upload /data/paddle-cache /app/app/logs /tmp/fault-analyzer-repos \
    && python -m pip check \
    && python -m compileall -q app.py celery_worker.py app bootstrap_schema.py init_database.py verify_runtime.py \
    && python verify_runtime.py --build \
    && python verify_runtime.py --ocr

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python verify_runtime.py --runtime || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "gunicorn -w ${WEB_CONCURRENCY:-4} -k ${GUNICORN_WORKER_CLASS:-gthread} --threads ${WEB_THREADS:-8} --timeout ${GUNICORN_TIMEOUT:-300} --bind 0.0.0.0:5000 'app:create_app()'"]

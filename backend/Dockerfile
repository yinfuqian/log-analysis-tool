ARG PYTHON_BASE_IMAGE=registry.cn-hangzhou.aliyuncs.com/k8s-docker-image-yfq/python:3.10-slim
FROM ${PYTHON_BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FLASK_APP=app.py

WORKDIR /app
ARG APT_MIRROR=https://mirrors.aliyun.com/debian
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}|g; s|http://security.debian.org/debian-security|${APT_MIRROR}-security|g" /etc/apt/sources.list.d/debian.sources; \
    elif [ -f /etc/apt/sources.list ]; then \
        sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}|g; s|http://security.debian.org/debian-security|${APT_MIRROR}-security|g" /etc/apt/sources.list; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -i "${PIP_INDEX_URL}" -r requirements.txt

COPY . .

RUN chmod +x /app/docker-entrypoint.sh /app/migrate_db.sh /app/start.sh /app/start_worker.sh \
    && mkdir -p /data/upload /app/app/logs /tmp/log-analyzer-repos \
    && python -m compileall -q app.py celery_worker.py app bootstrap_schema.py init_database.py

EXPOSE 5000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "gunicorn -w ${WEB_CONCURRENCY:-4} -k ${GUNICORN_WORKER_CLASS:-gthread} --threads ${WEB_THREADS:-8} --timeout ${GUNICORN_TIMEOUT:-300} --bind 0.0.0.0:5000 'app:create_app()'"]

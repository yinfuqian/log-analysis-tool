import os
from pathlib import Path
from urllib.parse import quote_plus


def load_dotenv_file(path, override=False):
    env_path = Path(path)
    if not env_path.exists():
        return

    parsed_values = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        parsed_values[key] = value

    for key, value in parsed_values.items():
        if override or key not in os.environ:
            os.environ[key] = value


def load_local_env():
    backend_dir = Path(__file__).resolve().parents[1]
    project_root = backend_dir.parent
    for env_file in (project_root / ".env", backend_dir / ".env"):
        load_dotenv_file(env_file, override=False)


load_local_env()


def _build_mysql_uri():
    username = os.getenv("MYSQL_USERNAME", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    database = os.getenv("MYSQL_DATABASE", "log_analyzer")
    return (
        f"mysql+pymysql://{quote_plus(username)}:{quote_plus(password)}"
        f"@{host}:{port}/{database}?charset=utf8mb4&ssl_disabled=true"
    )


def _build_redis_url():
    username = os.getenv("REDIS_USERNAME", "")
    password = os.getenv("REDIS_PASSWORD", "")
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    database = os.getenv("REDIS_DATABASE", "0")
    if username:
        auth = f"{quote_plus(username)}:{quote_plus(password)}@"
    elif password:
        auth = f":{quote_plus(password)}@"
    else:
        auth = ""
    return f"redis://{auth}{host}:{port}/{database}"

class Config:
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(120 * 1024 * 1024)))
    MAX_LOG_BYTES = int(os.getenv("MAX_LOG_BYTES", str(100 * 1024 * 1024)))
    MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))
    MAX_IMAGE_COUNT = int(os.getenv("MAX_IMAGE_COUNT", "10"))
    MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "40000000"))
    # 存储类型: 'local'（本地存储） | 'minio'（MinIO） | 'nas'（NAS）
    STORAGE_TYPE = os.getenv("STORAGE_TYPE", "local")

    # 本地存储路径
    LOCAL_STORAGE_DIR = os.getenv("LOCAL_STORAGE_DIR", "/data/upload")
    if not os.path.exists(LOCAL_STORAGE_DIR):
        os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)

    # MinIO 配置todo
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "")
    MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
    MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
    MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME", "logs")

    # NAS 配置 todo
    NAS_STORAGE_PATH = os.getenv("NAS_STORAGE_PATH", "/mnt/nas/logs")  # 挂载的 NAS 目录

    # 日志配置
    LOG_DIR = os.getenv("LOG_DIR", os.path.join(os.path.abspath(os.path.dirname(__file__)), "logs"))
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)

    LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", "DEBUG")
    LOGGING_FORMAT = os.getenv("LOGGING_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    LOGGING_FILE = os.getenv("LOGGING_FILE", os.path.join(LOG_DIR, "app.log"))

    # 数据库 & Redis 配置
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "log_analyzer")
    MYSQL_USERNAME = os.getenv("MYSQL_USERNAME", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI", _build_mysql_uri())
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("SQLALCHEMY_POOL_RECYCLE", "1800")),
    }
    REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT = os.getenv("REDIS_PORT", "6379")
    REDIS_DATABASE = os.getenv("REDIS_DATABASE", "0")
    REDIS_USERNAME = os.getenv("REDIS_USERNAME", "")
    REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
    REDIS_URL = os.getenv("REDIS_URL", _build_redis_url())
    REDIS_SOCKET_CONNECT_TIMEOUT = int(os.getenv("REDIS_SOCKET_CONNECT_TIMEOUT", "10"))
    REDIS_SOCKET_TIMEOUT = int(os.getenv("REDIS_SOCKET_TIMEOUT", "60"))
    REDIS_HEALTH_CHECK_INTERVAL = int(os.getenv("REDIS_HEALTH_CHECK_INTERVAL", "30"))
    CELERY_BROKER_SOCKET_TIMEOUT = int(os.getenv("CELERY_BROKER_SOCKET_TIMEOUT", "360"))

    # Authentication configuration
    AUTH_USERS_FILE = os.getenv("AUTH_USERS_FILE", "/data/users.csv")
    AUTH_LOGIN_MAX_FAILURES = int(os.getenv("AUTH_LOGIN_MAX_FAILURES", "5"))
    AUTH_LOGIN_WINDOW_SECONDS = int(os.getenv("AUTH_LOGIN_WINDOW_SECONDS", "300"))

    # Git 用户密码（敏感信息建议用环境变量）
    GIT_BASE_URL = os.getenv("GIT_BASE_URL", "")
    GIT_USER = os.getenv("GIT_USER", "")
    GIT_PASSWORD = os.getenv("GIT_PASSWORD", "")
    GITLAB_PRIVATE_TOKEN = os.getenv("GITLAB_PRIVATE_TOKEN", "")
    GITLAB_PROJECT_MEMBERSHIP_ONLY = os.getenv("GITLAB_PROJECT_MEMBERSHIP_ONLY", "false").lower() == "true"
    GITLAB_API_TIMEOUT = int(os.getenv("GITLAB_API_TIMEOUT", "30"))
    GITLAB_API_MAX_RETRIES = int(os.getenv("GITLAB_API_MAX_RETRIES", "3"))
    GITLAB_API_RETRY_DELAY = int(os.getenv("GITLAB_API_RETRY_DELAY", "1"))
    GITLAB_DB_MAX_RETRIES = int(os.getenv("GITLAB_DB_MAX_RETRIES", "2"))
    GITLAB_SYNC_SKIP_EXISTING_REPOS = os.getenv("GITLAB_SYNC_SKIP_EXISTING_REPOS", "true").lower() == "true"

    ## openai信息
    OPENAI_KEY = os.getenv("OPENAI_KEY", "")
    OPENAI_URL = os.getenv("OPENAI_URL", "https://api.deepseek.com")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "deepseek-chat")
    OPENAI_API_STYLE = os.getenv("OPENAI_API_STYLE", "chat").lower()
    LOG_ERROR_CONTEXT_LINES = int(os.getenv("LOG_ERROR_CONTEXT_LINES", "10"))
    LOG_CONTEXT_MAX_CHARS = int(os.getenv("LOG_CONTEXT_MAX_CHARS", "30000"))
    
    ## 日志格式
    LOG_CODE_PATTERNS = [
        r'([\w\.]+)\(([\w\.]+):(\d+)\)',           # com.zhuiyi.MyService(MyService.java:123)
        r'at\s+([\w\.]+)\(([\w\.]+):(\d+)\)',       # at com.zhuiyi.Handler(Handler.java:88)
        r'\[([\w\.]+)\]\[(\d+)\]',                 # [com.zhuiyi.auth.AuthInterceptor][43]
    ]
    
    ## 支持的文件类型
    SUPPORTED_LANGUAGES = ['.java']  # 支持的文件类型（根据需求调整）


    ## 异步配置
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', REDIS_URL)  # Redis 作为消息队列
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', REDIS_URL)  # Redis 作为结果存储
    CELERY_BROKER_POOL_LIMIT = int(os.getenv("CELERY_BROKER_POOL_LIMIT", "10"))
    CELERY_VISIBILITY_TIMEOUT = int(os.getenv("CELERY_VISIBILITY_TIMEOUT", "7200"))
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        "socket_keepalive": True,
        "socket_connect_timeout": REDIS_SOCKET_CONNECT_TIMEOUT,
        "socket_timeout": CELERY_BROKER_SOCKET_TIMEOUT,
        "retry_on_timeout": True,
        "health_check_interval": REDIS_HEALTH_CHECK_INTERVAL,
        "visibility_timeout": CELERY_VISIBILITY_TIMEOUT,
    }
    CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {
        "socket_connect_timeout": REDIS_SOCKET_CONNECT_TIMEOUT,
        "socket_timeout": REDIS_SOCKET_TIMEOUT,
        "retry_on_timeout": True,
        "health_check_interval": REDIS_HEALTH_CHECK_INTERVAL,
    }

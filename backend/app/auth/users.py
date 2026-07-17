import csv
import hashlib
import hmac
import logging
import threading
from dataclasses import dataclass
from pathlib import Path


def normalize_username(value):
    return str(value or "").strip().lower()


def build_credential_version(username, password):
    value = f"{normalize_username(username)}\0{str(password or '')}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class UserRecord:
    username: str
    password: str
    status: int
    credential_version: str

    @property
    def enabled(self):
        return self.status == 1


class UserStore:
    available = True
    required_columns = {"username", "password", "status"}

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.last_reload_error = None
        self._users = self._load_users()
        self._observed_identity = self._file_identity()

    def _file_identity(self):
        try:
            stat_result = self.path.stat()
            content_digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:
            return None
        return stat_result.st_mtime_ns, stat_result.st_size, content_digest

    def _load_users(self):
        users = {}
        with self.path.open("r", encoding="utf-8-sig", newline="") as file_obj:
            reader = csv.DictReader(file_obj)
            columns = {str(name or "").strip().lower() for name in (reader.fieldnames or [])}
            if not self.required_columns.issubset(columns):
                raise ValueError("用户 CSV 缺少必要字段: username,password,status")

            for line_number, item in enumerate(reader, start=2):
                username = normalize_username(item.get("username"))
                password = str(item.get("password") or "")
                raw_status = str(item.get("status") or "").strip()
                if not username:
                    raise ValueError(f"第 {line_number} 行用户名不能为空")
                if username in users:
                    raise ValueError(f"用户名重复: {username}")
                if not password:
                    raise ValueError(f"用户 {username} 的密码不能为空")
                if raw_status not in {"0", "1", "2"}:
                    raise ValueError(f"用户 {username} 的状态必须是 0、1 或 2")
                users[username] = UserRecord(
                    username=username,
                    password=password,
                    status=int(raw_status),
                    credential_version=build_credential_version(username, password),
                )
        return users

    def _reload_if_changed(self):
        identity = self._file_identity()
        if identity == self._observed_identity:
            return
        with self._lock:
            identity = self._file_identity()
            if identity == self._observed_identity:
                return
            self._observed_identity = identity
            try:
                users = self._load_users()
            except (OSError, ValueError, TypeError, csv.Error) as exc:
                self.last_reload_error = exc
                logging.getLogger(__name__).error("用户配置热加载失败: %s", exc)
                return
            self._users = users
            self.last_reload_error = None

    def get_user(self, username):
        self._reload_if_changed()
        return self._users.get(normalize_username(username))

    def verify_password(self, username, password):
        user = self.get_user(username)
        if not user or not user.enabled:
            return None
        if not hmac.compare_digest(user.password, str(password or "")):
            return None
        return user


class UnavailableUserStore:
    available = False

    def __init__(self, error):
        self.last_reload_error = error

    def get_user(self, username):
        return None

    def verify_password(self, username, password):
        return None

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from werkzeug.security import check_password_hash


def normalize_username(value):
    return str(value or "").strip().lower()


@dataclass(frozen=True)
class UserRecord:
    username: str
    password_hash: str
    enabled: bool
    credential_version: str


class UserStore:
    available = True

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.last_reload_error = None
        self._users = self._load_users()
        self._observed_identity = self._file_identity()

    def _file_identity(self):
        try:
            stat_result = self.path.stat()
        except OSError:
            return None
        return stat_result.st_mtime_ns, stat_result.st_size

    def _load_users(self):
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        users = {}
        for item in payload.get("users", []):
            username = normalize_username(item.get("username"))
            if not username:
                raise ValueError("用户名不能为空")
            if username in users:
                raise ValueError(f"用户名重复: {username}")
            password_hash = str(item.get("password_hash") or "")
            if not password_hash.startswith(("scrypt:", "pbkdf2:")):
                raise ValueError(f"用户 {username} 的密码哈希无效")
            users[username] = UserRecord(
                username=username,
                password_hash=password_hash,
                enabled=bool(item.get("enabled", True)),
                credential_version=str(item.get("credential_version") or "1"),
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
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
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
        if not check_password_hash(user.password_hash, str(password or "")):
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

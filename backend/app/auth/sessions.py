import hashlib
import json
import secrets
import time

from app.auth.users import normalize_username


class SessionService:
    def __init__(self, redis_client, user_store, max_failures=5, failure_window_seconds=300):
        self.redis = redis_client
        self.user_store = user_store
        self.max_failures = max(1, int(max_failures))
        self.failure_window_seconds = max(1, int(failure_window_seconds))

    @staticmethod
    def _token_key(raw_token):
        digest = hashlib.sha256(str(raw_token or "").encode("utf-8")).hexdigest()
        return f"auth:session:{digest}"

    @staticmethod
    def _failure_key(username, source_ip):
        identity = f"{normalize_username(username)}|{source_ip or 'unknown'}"
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return f"auth:login-failure:{digest}"

    def create(self, user):
        raw_token = secrets.token_urlsafe(32)
        payload = {
            "username": user.username,
            "credential_version": user.credential_version,
            "created_at": int(time.time()),
        }
        self.redis.set(self._token_key(raw_token), json.dumps(payload, ensure_ascii=False))
        return raw_token

    def authenticate(self, raw_token):
        if not raw_token:
            return None
        raw_payload = self.redis.get(self._token_key(raw_token))
        if not raw_payload:
            return None
        try:
            payload = json.loads(raw_payload)
        except (TypeError, ValueError):
            return None
        user = self.user_store.get_user(payload.get("username"))
        if not user or not user.enabled:
            return None
        if user.credential_version != str(payload.get("credential_version") or ""):
            return None
        return user

    def revoke(self, raw_token):
        if raw_token:
            self.redis.delete(self._token_key(raw_token))

    def register_failure(self, username, source_ip):
        key = self._failure_key(username, source_ip)
        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, self.failure_window_seconds)
        return count >= self.max_failures

    def clear_failures(self, username, source_ip):
        self.redis.delete(self._failure_key(username, source_ip))

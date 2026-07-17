import tempfile
import unittest
from pathlib import Path

from app.auth.sessions import SessionService
from app.auth.users import UserStore


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}

    def set(self, key, value):
        self.values[key] = str(value)

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)

    def incr(self, key):
        value = int(self.values.get(key, "0")) + 1
        self.values[key] = str(value)
        return value

    def expire(self, key, seconds):
        self.expirations[key] = seconds


class SessionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.users_path = Path(self.temp_dir.name) / "users.csv"
        self.write_user("secret", 1)
        self.users = UserStore(self.users_path)
        self.redis = FakeRedis()
        self.sessions = SessionService(self.redis, self.users, max_failures=2, failure_window_seconds=60)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_user(self, password, status):
        self.users_path.write_text(
            f"username,password,status\nalice,{password},{status}\n",
            encoding="utf-8",
        )

    def test_create_authenticate_and_revoke_session(self):
        token = self.sessions.create(self.users.get_user("alice"))

        self.assertEqual(self.sessions.authenticate(token).username, "alice")
        self.sessions.revoke(token)
        self.assertIsNone(self.sessions.authenticate(token))

    def test_password_change_invalidates_session(self):
        token = self.sessions.create(self.users.get_user("alice"))

        self.write_user("new-secret", 1)

        self.assertIsNone(self.sessions.authenticate(token))

    def test_status_zero_and_two_invalidate_session(self):
        for status in (0, 2):
            self.write_user("secret", 1)
            token = self.sessions.create(self.users.get_user("alice"))

            self.write_user("secret", status)

            self.assertIsNone(self.sessions.authenticate(token))

    def test_login_failures_are_rate_limited(self):
        self.assertFalse(self.sessions.register_failure("alice", "127.0.0.1"))
        self.assertTrue(self.sessions.register_failure("alice", "127.0.0.1"))


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from app.auth.users import UserStore


class UserStoreTests(unittest.TestCase):
    def test_loads_user_and_verifies_password(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            users_path = Path(temp_dir) / "users.json"
            users_path.write_text(
                json.dumps({
                    "users": [
                        {
                            "username": "Alice",
                            "password_hash": generate_password_hash("secret", method="scrypt"),
                            "enabled": True,
                            "credential_version": "1",
                        }
                    ]
                }),
                encoding="utf-8",
            )

            store = UserStore(users_path)

            user = store.verify_password(" alice ", "secret")
            self.assertIsNotNone(user)
            self.assertEqual(user.username, "alice")
            self.assertEqual(user.credential_version, "1")
            self.assertIsNone(store.verify_password("alice", "wrong"))

    def test_rejects_duplicate_normalized_usernames(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            users_path = Path(temp_dir) / "users.json"
            password_hash = generate_password_hash("secret", method="scrypt")
            users_path.write_text(
                json.dumps({
                    "users": [
                        {"username": "Alice", "password_hash": password_hash},
                        {"username": " alice ", "password_hash": password_hash},
                    ]
                }),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "用户名重复"):
                UserStore(users_path)

    def test_rejects_plaintext_passwords(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            users_path = Path(temp_dir) / "users.json"
            users_path.write_text(
                json.dumps({
                    "users": [
                        {"username": "alice", "password_hash": "secret"},
                    ]
                }),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "密码哈希"):
                UserStore(users_path)

    def test_invalid_hot_reload_keeps_last_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            users_path = Path(temp_dir) / "users.json"
            users_path.write_text(
                json.dumps({
                    "users": [{
                        "username": "alice",
                        "password_hash": generate_password_hash("secret", method="scrypt"),
                        "credential_version": "1",
                    }]
                }),
                encoding="utf-8",
            )
            store = UserStore(users_path)

            users_path.write_text("{broken", encoding="utf-8")

            user = store.get_user("alice")
            self.assertIsNotNone(user)
            self.assertEqual(user.credential_version, "1")
            self.assertIsNotNone(store.last_reload_error)

    def test_valid_hot_reload_replaces_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            users_path = Path(temp_dir) / "users.json"
            users_path.write_text(
                json.dumps({
                    "users": [{
                        "username": "alice",
                        "password_hash": generate_password_hash("secret", method="scrypt"),
                        "credential_version": "1",
                    }]
                }),
                encoding="utf-8",
            )
            store = UserStore(users_path)

            users_path.write_text(
                json.dumps({
                    "users": [{
                        "username": "alice",
                        "password_hash": generate_password_hash("new-secret", method="scrypt"),
                        "credential_version": "version-two",
                    }]
                }),
                encoding="utf-8",
            )

            user = store.get_user("alice")
            self.assertEqual(user.credential_version, "version-two")
            self.assertIsNone(store.verify_password("alice", "secret"))
            self.assertIsNotNone(store.verify_password("alice", "new-secret"))


if __name__ == "__main__":
    unittest.main()

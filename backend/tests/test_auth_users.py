import tempfile
import unittest
from pathlib import Path

from app.auth.users import UserStore


class UserStoreTests(unittest.TestCase):
    def write_csv(self, path, rows):
        path.write_text(
            "username,password,status\n" + "\n".join(rows) + "\n",
            encoding="utf-8",
        )

    def test_loads_csv_user_and_verifies_plaintext_password(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            self.write_csv(path, ["Alice,secret,1"])

            store = UserStore(path)

            user = store.verify_password(" alice ", "secret")
            self.assertEqual(user.username, "alice")
            self.assertEqual(user.status, 1)
            self.assertNotEqual(user.credential_version, "secret")
            self.assertIsNone(store.verify_password("alice", "wrong"))

    def test_status_zero_and_two_cannot_authenticate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            self.write_csv(path, ["disabled,secret,0", "forced,secret,2"])
            store = UserStore(path)

            self.assertIsNone(store.verify_password("disabled", "secret"))
            self.assertIsNone(store.verify_password("forced", "secret"))

    def test_rejects_duplicate_normalized_usernames(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            self.write_csv(path, ["Alice,one,1", " alice ,two,1"])

            with self.assertRaisesRegex(ValueError, "用户名重复"):
                UserStore(path)

    def test_rejects_invalid_status_and_missing_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            self.write_csv(path, ["alice,secret,9"])
            with self.assertRaisesRegex(ValueError, "状态"):
                UserStore(path)

            path.write_text("username,password\nalice,secret\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "字段"):
                UserStore(path)

    def test_invalid_hot_reload_keeps_last_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            self.write_csv(path, ["alice,secret,1"])
            store = UserStore(path)

            path.write_text("broken", encoding="utf-8")

            self.assertIsNotNone(store.verify_password("alice", "secret"))
            self.assertIsNotNone(store.last_reload_error)

    def test_valid_hot_reload_replaces_password_status_and_deleted_users(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            self.write_csv(path, ["alice,secret,1", "bob,password,1"])
            store = UserStore(path)
            old_version = store.get_user("alice").credential_version

            self.write_csv(path, ["alice,new-secret,2"])

            alice = store.get_user("alice")
            self.assertNotEqual(alice.credential_version, old_version)
            self.assertIsNone(store.verify_password("alice", "new-secret"))
            self.assertIsNone(store.get_user("bob"))


if __name__ == "__main__":
    unittest.main()

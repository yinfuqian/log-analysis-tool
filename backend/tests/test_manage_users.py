import unittest

from manage_users import build_password_hash
from werkzeug.security import check_password_hash


class ManageUsersTests(unittest.TestCase):
    def test_build_password_hash_uses_scrypt(self):
        password_hash = build_password_hash("secret")

        self.assertTrue(password_hash.startswith("scrypt:"))
        self.assertTrue(check_password_hash(password_hash, "secret"))


if __name__ == "__main__":
    unittest.main()

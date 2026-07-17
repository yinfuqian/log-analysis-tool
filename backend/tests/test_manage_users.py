import tempfile
import unittest
from pathlib import Path

from manage_users import validate_users_file


class ManageUsersTests(unittest.TestCase):
    def test_validates_csv_and_returns_user_count(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "users.csv"
            path.write_text(
                "username,password,status\nalice,secret,1\nbob,password,0\n",
                encoding="utf-8",
            )

            self.assertEqual(validate_users_file(path), 2)


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
import unittest

from app.auth.users import UserStore


class DefaultUsersCsvTests(unittest.TestCase):
    def test_default_admin_user_is_enabled(self):
        project_dir = Path(__file__).resolve().parents[2]
        users_path = project_dir / "users.csv"
        store = UserStore(users_path)

        user = store.verify_password("admin", "admin123")

        self.assertIsNotNone(user)
        self.assertEqual(user.status, 1)

        compose_text = (project_dir / "docker-compose.yml").read_text(encoding="utf-8")
        # Compose 使用 YAML 锚点集中声明一次，再由 migrate、api、worker 三个服务复用。
        self.assertEqual(compose_text.count("./users.csv:/data/users.csv:ro"), 1)
        self.assertEqual(compose_text.count("AUTH_USERS_FILE: /data/users.csv"), 1)
        self.assertEqual(compose_text.count("volumes: *backend-volumes"), 3)
        self.assertEqual(compose_text.count("environment: *backend-environment"), 3)


if __name__ == "__main__":
    unittest.main()

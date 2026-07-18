import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class HealthRoutesTests(unittest.TestCase):
    def test_ready_returns_503_with_check_details_when_runtime_is_not_ready(self):
        from flask import Flask
        from app.health.routes import health_bp

        app = Flask(__name__)
        app.register_blueprint(health_bp, url_prefix="/health")
        with patch(
            "app.health.routes.run_readiness_checks",
            return_value={
                "ready": False,
                "checks": {"database": {"ok": False, "message": "数据库不可用"}},
            },
        ):
            response = app.test_client().get("/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "unavailable")
        self.assertIn("database", response.get_json()["checks"])

    def test_live_does_not_run_external_dependency_checks(self):
        from flask import Flask
        from app.health.routes import health_bp

        app = Flask(__name__)
        app.register_blueprint(health_bp, url_prefix="/health")
        with patch("app.health.routes.run_readiness_checks") as checker:
            response = app.test_client().get("/health/live")

        self.assertEqual(response.status_code, 200)
        checker.assert_not_called()


if __name__ == "__main__":
    unittest.main()

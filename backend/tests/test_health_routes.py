import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


STUBBED_TOP_LEVEL_MODULES = ("app", "flask", "openai", "celery", "extensions")


def purge_stubbed_modules():
    """剔除其他测试模块遗留在 sys.modules 中的桩模块，保证导入真实实现。

    仓库里部分用例用 types.ModuleType 顶替 app/flask 等模块且不做还原，
    unittest discover 到本模块时 sys.modules 可能已被污染，因此导入前先清理。
    """
    for name in list(sys.modules):
        if name.split(".")[0] not in STUBBED_TOP_LEVEL_MODULES:
            continue
        module = sys.modules.get(name)
        if module is None or getattr(module, "__file__", None):
            continue
        sys.modules.pop(name, None)


class HealthRoutesTests(unittest.TestCase):
    def test_ready_returns_503_with_check_details_when_runtime_is_not_ready(self):
        purge_stubbed_modules()
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
        purge_stubbed_modules()
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

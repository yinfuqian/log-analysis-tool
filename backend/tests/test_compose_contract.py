import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = PROJECT_ROOT / "docker-compose.yml"


class ComposeContractTests(unittest.TestCase):
    def test_compose_declares_complete_fault_analysis_service_graph(self):
        source = COMPOSE_PATH.read_text(encoding="utf-8")

        for service in ("mysql", "redis", "migrate", "api", "worker", "frontend"):
            self.assertRegex(source, rf"(?m)^  {re.escape(service)}:\s*$")

    def test_compose_uses_health_based_startup_dependencies(self):
        source = COMPOSE_PATH.read_text(encoding="utf-8")

        self.assertIn("condition: service_healthy", source)
        self.assertIn("condition: service_completed_successfully", source)
        self.assertGreaterEqual(source.count("healthcheck:"), 5)

    def test_compose_persists_database_redis_ocr_and_runtime_data(self):
        source = COMPOSE_PATH.read_text(encoding="utf-8")

        for volume in (
            "mysql-data",
            "redis-data",
            "ocr-models",
            "uploads",
            "runtime-logs",
            "repo-cache",
        ):
            self.assertIn(f"{volume}:", source)

    def test_env_example_has_unique_local_build_defaults(self):
        """示例配置不能用重复键意外覆盖本地可构建默认值。"""
        source = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        keys = [
            line.split("=", 1)[0].strip()
            for line in source.splitlines()
            if line.strip() and not line.lstrip().startswith("#") and "=" in line
        ]

        self.assertEqual(len(keys), len(set(keys)))
        self.assertIn("PYTHON_BASE_IMAGE=docker.m.daocloud.io/library/python:3.10-slim-bookworm", source)
        self.assertIn("BACKEND_IMAGE=fault-analysis-backend:latest", source)
        self.assertIn("FRONTEND_IMAGE=fault-analysis-frontend:latest", source)


if __name__ == "__main__":
    unittest.main()

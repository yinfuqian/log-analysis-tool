import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class DockerContractTests(unittest.TestCase):
    def test_backend_image_runs_dependency_application_worker_and_ocr_checks(self):
        source = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("python -m pip check", source)
        self.assertIn("python verify_runtime.py --build", source)
        self.assertIn("python verify_runtime.py --ocr", source)
        self.assertIn("HEALTHCHECK", source)
        self.assertIn("PADDLE_PDX_CACHE_HOME=/data/paddle-cache", source)
        self.assertIn("libgl1", source)
        self.assertIn("libglib2.0-0", source)

    def test_frontend_image_is_a_tested_node20_nginx_production_build(self):
        source = (PROJECT_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("node:20", source)
        self.assertIn("npm ci", source)
        self.assertIn("npm run test:unit", source)
        self.assertIn("npm run build", source)
        self.assertIn("nginx:", source)
        self.assertIn("HEALTHCHECK", source)

    def test_docker_contexts_exclude_secrets_and_generated_data(self):
        backend_ignore = (PROJECT_ROOT / "backend" / ".dockerignore").read_text(encoding="utf-8")
        frontend_ignore = (PROJECT_ROOT / "frontend" / ".dockerignore").read_text(encoding="utf-8")

        self.assertIn(".env", backend_ignore)
        self.assertIn(".venv", backend_ignore)
        self.assertIn("node_modules", frontend_ignore)
        self.assertIn("dist", frontend_ignore)

    def test_frontend_docker_context_keeps_webpack_build_helpers(self):
        """Webpack 的源码辅助目录必须进入镜像构建上下文。"""
        frontend_ignore = (PROJECT_ROOT / "frontend" / ".dockerignore").read_text(encoding="utf-8")
        active_rules = {
            line.strip()
            for line in frontend_ignore.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertNotIn("build", active_rules)
        self.assertNotIn("app/log-analyze/build", active_rules)
        self.assertTrue((PROJECT_ROOT / "frontend" / "app" / "log-analyze" / "build" / "chunkName.js").is_file())

    def test_frontend_nginx_defers_api_resolution_to_container_dns(self):
        """Nginx 配置检查不应依赖 Compose 网络已提前创建。"""
        source = (PROJECT_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")

        self.assertIn("resolver 127.0.0.11", source)
        self.assertIn("set $api_upstream http://api:5000", source)
        self.assertIn("rewrite ^/api/(.*)$ /$1 break", source)
        self.assertIn("proxy_pass $api_upstream", source)

    def test_backend_installs_mysql8_rsa_authentication_dependencies(self):
        """MySQL 8 默认认证方式需要 PyMySQL 的 RSA 扩展。"""
        requirements = (PROJECT_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("PyMySQL[rsa]==1.1.1", requirements)


if __name__ == "__main__":
    unittest.main()

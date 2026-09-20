import re
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
        local_compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("resolver 127.0.0.11", source)
        self.assertIn("set $api_upstream ${API_UPSTREAM}", source)
        self.assertIn("API_UPSTREAM: http://api:5000", local_compose)
        self.assertIn("rewrite ^/api/(.*)$ /$1 break", source)
        self.assertIn("proxy_pass $api_upstream", source)

    def test_backend_installs_mysql8_rsa_authentication_dependencies(self):
        """MySQL 8 默认认证方式需要 PyMySQL 的 RSA 扩展。"""
        requirements = (PROJECT_ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8")

        self.assertIn("PyMySQL[rsa]==1.1.1", requirements)

    def test_backend_shell_scripts_are_normalized_for_linux(self):
        """仓库和镜像构建都必须阻止 Windows CRLF 破坏 Linux 入口脚本。"""
        dockerfile = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
        attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")

        self.assertIn("*.sh text eol=lf", attributes)
        self.assertIn("find /app -type f -name '*.sh' -exec sed -i 's/\\r$//' {} +", dockerfile)

    def test_backend_image_ships_attachment_unpack_tools(self):
        """解压工具必须随镜像发布，避免技能执行时再联网安装。"""
        dockerfile = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

        # bsdtar（libarchive-tools）负责 RAR/7z，unzip 兜底 zip；7-Zip 系命令按发行版包名择一安装。
        self.assertIn("unzip libarchive-tools", dockerfile)
        self.assertIn("p7zip-full", dockerfile)
        self.assertIn("7zip", dockerfile)
        # 构建期断言：镜像里必须真的能调用这几个命令，否则构建直接失败。
        self.assertIn("command -v bsdtar >/dev/null", dockerfile)
        self.assertIn("command -v unzip >/dev/null", dockerfile)

    def test_backend_image_installs_system_dependencies_from_offline_debs(self):
        """后端镜像必须优先使用仓库内离线 deb 包，避免内网构建时依赖 apt 源。"""
        source = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("--mount=type=bind,source=offline/apt", source)
        self.assertIn("使用仓库内离线 deb 包安装系统依赖", source)

        packages_match = re.search(r'ARG APT_PACKAGES="([^"]+)"', source)
        self.assertIsNotNone(packages_match, "Dockerfile 必须声明 ARG APT_PACKAGES 系统依赖清单")
        packages = packages_match.group(1).split()

        bundle = PROJECT_ROOT / "backend" / "offline" / "apt" / "bookworm-amd64"
        manifest_path = bundle / "MANIFEST.tsv"
        self.assertTrue(manifest_path.is_file(), f"缺少离线依赖清单：{manifest_path}")

        bundled = {
            line.split("\t")[0]
            for line in manifest_path.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        }
        for package in packages:
            self.assertIn(package, bundled, f"离线 deb 包缺少系统依赖：{package}")
        # 清单与 deb 包必须一一对应，避免残留过期包。
        self.assertEqual(len(list(bundle.glob("*.deb"))), len(bundled))

    def test_offline_apt_tooling_is_executable_inside_linux_containers(self):
        """离线 apt 依赖的下载与校验脚本必须在 Linux 容器内可直接执行。"""
        for name in ("apt-offline-download.sh", "apt-offline-verify.sh"):
            data = (PROJECT_ROOT / "scripts" / name).read_bytes()
            self.assertTrue(data, f"缺少脚本：{name}")
            self.assertNotIn(b"\r", data, f"{name} 必须使用 LF 行尾")

        exporter = (PROJECT_ROOT / "scripts" / "export_apt_offline_packages.ps1").read_text(encoding="utf-8")
        self.assertIn("apt-offline-download.sh", exporter)
        self.assertIn("apt-offline-verify.sh", exporter)
        self.assertIn("--platform", exporter)
        self.assertIn("--network", exporter)


if __name__ == "__main__":
    unittest.main()

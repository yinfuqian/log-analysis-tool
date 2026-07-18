"""生产镜像部署合同测试，防止生产服务器重新依赖源码构建。"""

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ProductionDeploymentContractTests(unittest.TestCase):
    """验证生产 Compose、运行镜像和发布脚本的安全边界。"""

    def test_production_compose_only_uses_prebuilt_application_images(self):
        """生产 Compose 只能引用镜像，不能构建源码或启动本地数据库。"""
        path = PROJECT_ROOT / "docker-compose.prod.yml"
        self.assertTrue(path.is_file())
        source = path.read_text(encoding="utf-8")

        self.assertNotIn("build:", source)
        self.assertNotRegex(source, r"(?m)^  (mysql|redis):\s*$")
        for service in ("migrate", "api", "worker", "frontend"):
            self.assertRegex(source, rf"(?m)^  {re.escape(service)}:\s*$")
        self.assertEqual(source.count("image: ${BACKEND_IMAGE:?"), 3)
        self.assertEqual(source.count("image: ${FRONTEND_IMAGE:?"), 1)

    def test_backend_runtime_stage_copies_only_runtime_files(self):
        """后端最终阶段必须使用白名单复制并要求外部用户表。"""
        dockerfile = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
        ignore = (PROJECT_ROOT / "backend" / ".dockerignore").read_text(encoding="utf-8")

        self.assertIn("AS build", dockerfile)
        self.assertIn("AS runtime", dockerfile)
        self.assertIn("COPY --from=build /app/app /app/app", dockerfile)
        self.assertIn("AUTH_USERS_FILE=/data/users.csv", dockerfile)
        self.assertIn("users.csv", ignore.splitlines())

    def test_backend_build_removes_generated_logs_and_python_caches(self):
        """构建自检生成的日志和 Python 缓存不能被复制到最终运行镜像。"""
        dockerfile = (PROJECT_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("rm -rf /app/app/logs/*", dockerfile)
        self.assertIn("-name '__pycache__'", dockerfile)

    def test_production_deploy_bundle_and_release_scripts_exist(self):
        """生产交付物只能包含部署文件，镜像构建和导出由独立脚本完成。"""
        required_files = (
            "deploy/.env.production.example",
            "deploy/users.example.csv",
            "deploy/README.md",
            "scripts/build_release_images.ps1",
            "scripts/export_release_image.ps1",
            "scripts/package_production_deploy.ps1",
        )
        for relative_path in required_files:
            self.assertTrue((PROJECT_ROOT / relative_path).is_file(), relative_path)

        build_script = (PROJECT_ROOT / "scripts" / "build_release_images.ps1").read_text(encoding="utf-8")
        export_script = (PROJECT_ROOT / "scripts" / "export_release_image.ps1").read_text(encoding="utf-8")
        package_script = (PROJECT_ROOT / "scripts" / "package_production_deploy.ps1").read_text(encoding="utf-8")
        self.assertIn('ValidateSet("all", "backend", "frontend")', build_script)
        self.assertIn("docker push", build_script)
        self.assertIn("docker save", export_script)
        self.assertIn("docker-compose.prod.yml", package_script)
        self.assertNotIn("backend/app", package_script)

    def test_production_environment_example_is_not_git_ignored(self):
        """生产环境示例必须能提交，同时真实生产环境文件继续由通用规则忽略。"""
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("!deploy/.env.production.example", gitignore.splitlines())


if __name__ == "__main__":
    unittest.main()

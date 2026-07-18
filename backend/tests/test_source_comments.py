import importlib.util
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUDITOR_PATH = PROJECT_ROOT / "scripts" / "check_source_comments.py"
COMMENT_ADDER_PATH = PROJECT_ROOT / "scripts" / "add_source_comments.py"


def load_auditor_module():
    """从脚本路径加载注释审计模块，避免依赖 scripts 包初始化文件。"""
    spec = importlib.util.spec_from_file_location("check_source_comments", AUDITOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_comment_adder_module():
    """加载机械补全中文维护说明的脚本模块。"""
    spec = importlib.util.spec_from_file_location("add_source_comments", COMMENT_ADDER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SourceCommentAuditTests(unittest.TestCase):
    def test_python_audit_reports_missing_module_class_and_function_docs(self):
        auditor = load_auditor_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "sample.py"
            source_path.write_text("class Sample:\n    def run(self):\n        return True\n", encoding="utf-8")

            issues = auditor.audit_python_file(source_path)

        messages = [issue.message for issue in issues]
        self.assertTrue(any("模块" in message for message in messages))
        self.assertTrue(any("类 Sample" in message for message in messages))
        self.assertTrue(any("函数 run" in message for message in messages))

    def test_python_audit_accepts_chinese_responsibility_docs(self):
        auditor = load_auditor_module()
        source = '''"""示例模块负责验证中文维护说明。"""

class Sample:
    """表示可执行的示例对象。"""

    def run(self):
        """执行示例逻辑并返回成功状态。"""
        return True
'''
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "sample.py"
            source_path.write_text(source, encoding="utf-8")

            issues = auditor.audit_python_file(source_path)

        self.assertEqual(issues, [])

    def test_web_audit_requires_a_chinese_file_responsibility_comment(self):
        auditor = load_auditor_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "client.js"
            source_path.write_text("export const value = true\n", encoding="utf-8")

            issues = auditor.audit_text_file(source_path)

        self.assertEqual(len(issues), 1)
        self.assertIn("文件职责", issues[0].message)

    def test_file_discovery_prunes_ignored_directories_before_scanning(self):
        auditor = load_auditor_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "source.py").write_text('"""生产模块。"""\n', encoding="utf-8")
            ignored = root / ".venv"
            ignored.mkdir()
            (ignored / "dependency.py").write_text("broken = True\n", encoding="utf-8")

            files = list(auditor.iter_source_files(root, {".py"}))

        self.assertEqual([path.name for path in files], ["source.py"])

    def test_comment_adder_inserts_chinese_module_class_and_function_docs(self):
        adder = load_comment_adder_module()
        source = "class Worker:\n    def build_result(self):\n        return True\n"

        transformed = adder.transform_python_source(source, Path("worker.py"))
        compile(transformed, "worker.py", "exec")

        self.assertIn("模块负责", transformed)
        self.assertIn("Worker 类", transformed)
        self.assertIn("构建", transformed)

    def test_comment_adder_adds_vue_file_responsibility_comment(self):
        adder = load_comment_adder_module()

        transformed = adder.transform_text_source("<template><main /></template>\n", Path("Dashboard.vue"))

        self.assertTrue(transformed.startswith("<!-- Dashboard 页面组件负责"))

    def test_comment_adder_places_outer_doc_before_nested_function_decorators(self):
        adder = load_comment_adder_module()
        source = "def install(app):\n    @app.before_request\n    def handler():\n        return None\n"

        transformed = adder.transform_python_source(source, Path("middleware.py"))

        compile(transformed, "middleware.py", "exec")
        self.assertLess(transformed.index("注册或配置 install"), transformed.index("@app.before_request"))

    def test_comment_adder_does_not_confuse_chinese_code_with_chinese_comment(self):
        adder = load_comment_adder_module()
        source = "// api client\nexport const title = '故障分析工具'\n"

        transformed = adder.transform_text_source(source, Path("client.js"))

        self.assertTrue(transformed.startswith("/** client 模块负责"))


if __name__ == "__main__":
    unittest.main()

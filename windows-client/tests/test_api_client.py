import importlib.util
import inspect
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
import requests
import json


CLIENT_PATH = Path(__file__).resolve().parents[1] / "log_analyzer_client.py"


def load_client_module():
    spec = importlib.util.spec_from_file_location("log_analyzer_client_under_test", CLIENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.posts = []
        self.gets = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith("/git/sync-projects"):
            return FakeResponse({
                "message": "GitLab \u9879\u76ee\u540c\u6b65\u5b8c\u6210",
                "synced_projects": 3,
                "created_products": 1,
            })
        if url.endswith("/analysis/task/task-123/cancel"):
            return FakeResponse({
                "task_id": "task-123",
                "state": "REVOKED",
                "message": "\u4efb\u52a1\u5df2\u8bf7\u6c42\u53d6\u6d88",
            })
        if url.endswith("/analysis/discover_related_modules"):
            return FakeResponse({
                "status": "need_related_evidence",
                "requiresRelatedEvidence": True,
                "message": "\u8bc6\u522b\u5230\u6d89\u53ca\u4e0a\u4e0b\u6e38\u94fe\u8def",
                "reason": "\u65e5\u5fd7\u4e2d\u51fa\u73b0 HTTP 500",
                "issueSummary": "HTTP 500 from downstream service",
            })
        if url.endswith("/analysis/assess_related_code"):
            return FakeResponse({
                "status": "need_related_evidence",
                "requiresRelatedEvidence": True,
                "chainOwner": "downstream",
                "message": "版本代码判断此问题可能由下游出现",
            })
        if url.endswith("/analysis/submit_async"):
            return FakeResponse({
                "ok": True,
                "task_id": "task-123",
                "state": "PENDING",
                "status_url": "/analysis/task/task-123",
            })
        return FakeResponse({"ok": True, "url": url})

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if url.endswith("/analysis/task/task-123"):
            return FakeResponse({
                "task_id": "task-123",
                "state": "SUCCESS",
                "ready": True,
                "successful": True,
                "result": {"code_analysis": "done"},
            })
        if url.endswith("/git/branches"):
            return FakeResponse({
                "branches": ["master", "feature/log-analyzer"],
                "tags": ["v1.1.0", "v5.136.7-ZYKJ20230046-rc1"],
                "versions": ["master", "feature/log-analyzer", "v1.1.0", "v5.136.7-ZYKJ20230046-rc1"],
            })
        return FakeResponse({
            "products": [{"id": 1, "name": "bot"}],
            "modules": [{
                "module_id": 2,
                "module_name": "dialog",
                "branch": {
                    "branch_address": "https://git.example/repo.git",
                    "tag_version": "v1",
                },
            }],
        })


class ApiClientTests(unittest.TestCase):
    def test_client_branding_uses_fault_analysis_name(self):
        module = load_client_module()

        self.assertEqual(module.PRODUCT_NAME, "故障分析工具")
        self.assertIn("故障分析工具", module.APP_RELEASE_LABEL)
        self.assertNotIn("日志分析客户端", module.APP_RELEASE_LABEL)

    def test_formats_http_error_with_backend_json_reason(self):
        module = load_client_module()
        response = FakeResponse({
            "error": "缂哄皯蹇呰瀛楁",
            "missing_fields": ["image_tag", "file_path"],
        }, status_code=400)
        error = requests.HTTPError("400 Error", response=response)

        message = module.format_exception_message(error)

        self.assertIn("缂哄皯蹇呰瀛楁", message)
        self.assertIn("image_tag", message)
        self.assertNotIn("None", message)

    def test_formats_empty_exception_without_none_text(self):
        module = load_client_module()

        message = module.format_exception_message(Exception())

        self.assertIn("\u672a\u77e5\u9519\u8bef", message)
        self.assertNotIn("None", message)

    def test_notice_text_includes_scope_and_usage_scenarios(self):
        module = load_client_module()

        notice_text = module.build_notice_text()

        self.assertIn("\u9002\u7528\u8303\u56f4", notice_text)
        self.assertIn("\u4f7f\u7528\u573a\u666f", notice_text)
        self.assertIn(module.DEFAULT_BACKEND_URL, notice_text)

    def test_notice_text_can_be_loaded_from_config_file(self):
        module = load_client_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "notice_config.json"
            config_path.write_text(
                """
                {
                  "title": "自定义公告/{app_version}",
                  "lines": [
                    "第一行：{backend_url}",
                    "第二行：可随时调整"
                  ]
                }
                """,
                encoding="utf-8",
            )
            original_paths = module.NOTICE_CONFIG_PATHS
            module.NOTICE_CONFIG_PATHS = [config_path]
            try:
                title = module.build_notice_title()
                notice_text = module.build_notice_text()
            finally:
                module.NOTICE_CONFIG_PATHS = original_paths

        self.assertEqual(title, f"自定义公告/{module.APP_VERSION}")
        self.assertIn(f"第一行：{module.DEFAULT_BACKEND_URL}", notice_text)
        self.assertIn("第二行：可随时调整", notice_text)

    def test_api_assesses_chain_and_submits_related_evidence(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://backend", session=session)

        discovery = client.discover_related_modules(
            "1",
            "2",
            "https://git.example/primary.git",
            "v1",
            "/data/upload/demo.log",
        )
        code_decision = client.assess_related_code(
            "1",
            "2",
            "https://git.example/primary.git",
            "v1",
            "/data/upload/demo.log",
            [{
                "moduleId": "3",
                "moduleName": "dialogos",
                "role": "downstream",
                "branchAddress": "https://git.example/dialogos.git",
                "tagVersion": "v2",
            }],
        )
        task = client.submit_analysis_task(
            "1",
            "2",
            "https://git.example/primary.git",
            "v1",
            "/data/upload/demo.log",
            related_modules=[{
                "moduleId": "3",
                "moduleName": "dialogos",
                "role": "downstream",
                "branchAddress": "https://git.example/dialogos.git",
                "tagVersion": "v2",
            }],
            related_evidence=[{
                "label": "\u4e0b\u6e38\u65e5\u5fd7",
                "source_type": "file",
                "file_path": "/data/upload/downstream.log",
            }],
            skipped_chain_issues=[{
                "issueSummary": "asr transform error",
                "reason": "用户跳过补充条件",
            }],
        )

        self.assertTrue(discovery["requiresRelatedEvidence"])
        self.assertEqual(code_decision["chainOwner"], "downstream")
        self.assertEqual(task["task_id"], "task-123")
        discover_payload = session.posts[-3][1]["json"]
        code_payload = session.posts[-2][1]["json"]
        submit_payload = session.posts[-1][1]["json"]
        self.assertEqual(discover_payload["branchAddress"], "https://git.example/primary.git")
        self.assertEqual(code_payload["relatedModules"][0]["role"], "downstream")
        self.assertEqual(submit_payload["relatedModules"][0]["moduleName"], "dialogos")
        self.assertEqual(submit_payload["relatedEvidence"][0]["file_path"], "/data/upload/downstream.log")
        self.assertEqual(submit_payload["skippedChainIssues"][0]["issueSummary"], "asr transform error")

    def test_build_related_module_selection_items_uses_loaded_module_git_info(self):
        module = load_client_module()
        items = module.build_related_module_selection_items(
            [{
                "moduleId": "3",
                "moduleName": "dialogos",
                "role": "related",
                "reason": "\u4e3b\u6a21\u5757\u4ee3\u7801\u547d\u4e2d",
            }],
            [{
                "module_id": 3,
                "module_name": "dialogos",
                "branch": {
                    "branch_address": "https://git.example/dialogos.git",
                    "tag_version": "release-1",
                },
            }],
            {"https://git.example/dialogos.git": ["release-2", "release-1"]},
        )

        self.assertEqual(items[0]["moduleName"], "dialogos")
        self.assertEqual(items[0]["branchAddress"], "https://git.example/dialogos.git")
        self.assertEqual(items[0]["tagVersion"], "release-1")
        self.assertEqual(items[0]["versions"], ["release-2", "release-1"])

    def test_build_related_code_module_candidates_excludes_primary_module(self):
        module = load_client_module()
        candidates = module.build_related_code_module_candidates(
            [
                {
                    "module_id": 1,
                    "module_name": "algorithm-platform",
                    "branch": {"branch_address": "https://git.example/main.git", "tag_version": "v1"},
                },
                {
                    "module_id": 2,
                    "module_name": "dialogos",
                    "branch": {"branch_address": "https://git.example/dialogos.git", "tag_version": "release-1"},
                },
            ],
            primary_module_id="1",
            branch_versions={"https://git.example/dialogos.git": ["release-2"]},
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["moduleName"], "dialogos")
        self.assertEqual(candidates[0]["versions"], ["release-1", "release-2"])
        self.assertEqual(candidates[0]["branchOptions"], ["https://git.example/dialogos.git"])

    def test_build_related_code_module_candidates_marks_suggested_module_without_repo(self):
        module = load_client_module()
        candidates = module.build_related_code_module_candidates(
            [
                {
                    "module_id": 1,
                    "module_name": "manifest",
                    "branch": {"branch_address": "https://git.example/manifest.git", "tag_version": "v1"},
                },
                {
                    "module_id": 2,
                    "module_name": "asr",
                    "branch": None,
                },
            ],
            primary_module_id="1",
            suggested_modules=[{
                "moduleId": "2",
                "moduleName": "asr",
                "role": "downstream",
                "reason": "日志命中 asr",
            }],
        )

        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]["autoSelect"])
        self.assertEqual(candidates[0]["role"], "downstream")
        self.assertFalse(candidates[0]["repositoryAvailable"])
        self.assertIn("仓库", candidates[0]["repositoryMessage"])
        self.assertEqual(candidates[0]["branchOptions"], [])

    def test_build_related_code_module_candidates_keeps_missing_suggested_module(self):
        module = load_client_module()
        candidates = module.build_related_code_module_candidates(
            [{"module_id": 1, "module_name": "manifest", "branch": {"branch_address": "git://manifest", "tag_version": "v1"}}],
            primary_module_id="1",
            suggested_modules=[{
                "moduleId": "",
                "moduleName": "see-task",
                "role": "downstream",
                "reason": "日志命中疑似模块",
            }],
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["moduleName"], "see-task")
        self.assertTrue(candidates[0]["autoSelect"])
        self.assertFalse(candidates[0]["repositoryAvailable"])

    def test_build_related_code_module_candidates_matches_suggested_module_by_repo_slug(self):
        module = load_client_module()
        candidates = module.build_related_code_module_candidates(
            [
                {
                    "module_id": 246,
                    "module_name": "manifest",
                    "branch": {"branch_address": "https://code.example/see/manifest.git", "tag_version": "v1"},
                },
                {
                    "module_id": 252,
                    "module_name": "see-task",
                    "branch": {"branch_address": "https://code.example/see/see-task.git", "tag_version": "v2.10.1-rc54"},
                },
            ],
            primary_module_id="246",
            branch_versions={"https://code.example/see/see-task.git": ["v2.10.1-rc54", "v2.10.0"]},
            suggested_modules=[{
                "moduleId": "",
                "moduleName": "see-task",
                "role": "downstream",
                "reason": "日志包名命中 see-task",
            }],
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["moduleId"], "252")
        self.assertEqual(candidates[0]["moduleName"], "see-task")
        self.assertTrue(candidates[0]["autoSelect"])
        self.assertTrue(candidates[0]["repositoryAvailable"])
        self.assertEqual(candidates[0]["branchAddress"], "https://code.example/see/see-task.git")
        self.assertEqual(candidates[0]["versions"], ["v2.10.1-rc54", "v2.10.0"])

    def test_build_related_code_module_candidates_fuzzy_matches_zhuiyi_see_to_see_repo(self):
        module = load_client_module()
        candidates = module.build_related_code_module_candidates(
            [
                {
                    "module_id": 246,
                    "module_name": "manifest",
                    "branch": {"branch_address": "https://code.example/see/manifest.git", "tag_version": "v1"},
                },
                {
                    "module_id": 252,
                    "module_name": "see-task",
                    "branch": {"branch_address": "https://code.example/see/see-task.git", "tag_version": "v2.10.1-rc54"},
                },
            ],
            primary_module_id="246",
            suggested_modules=[{
                "moduleId": "",
                "moduleName": "zhuiyi-see",
                "role": "downstream",
                "reason": "日志 URL 命中 zhuiyi-see",
            }],
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["moduleId"], "252")
        self.assertEqual(candidates[0]["moduleName"], "see-task")
        self.assertTrue(candidates[0]["repositoryAvailable"])

    def test_build_related_code_module_candidates_drops_infrastructure_suggestions_without_repo_match(self):
        module = load_client_module()
        candidates = module.build_related_code_module_candidates(
            [
                {
                    "module_id": 246,
                    "module_name": "manifest",
                    "branch": {"branch_address": "https://code.example/see/manifest.git", "tag_version": "v1"},
                },
            ],
            primary_module_id="246",
            suggested_modules=[
                {"moduleName": "minio-cluster", "role": "downstream"},
                {"moduleName": "zhuiyi-see", "role": "downstream"},
                {"moduleName": "asr", "role": "downstream"},
            ],
        )

        missing_names = [candidate["moduleName"] for candidate in candidates if candidate["autoSelect"]]

        self.assertEqual(missing_names, ["asr"])

    def test_build_related_code_module_candidates_uses_remote_versions_for_matched_repo(self):
        module = load_client_module()
        candidates = module.build_related_code_module_candidates(
            [
                {
                    "module_id": 253,
                    "module_name": "see-dataset",
                    "branch": {
                        "branch_address": "https://code.in.wezhuiyi.com/see/see-dataset.git",
                        "tag_version": "master",
                    },
                },
            ],
            primary_module_id="246",
            branch_versions={
                "https://code.in.wezhuiyi.com/see/see-dataset.git": ["release-2.0", "master"],
            },
            suggested_modules=[{
                "moduleName": "see-dataset",
                "role": "downstream",
            }],
        )

        self.assertEqual(candidates[0]["branchAddress"], "https://code.in.wezhuiyi.com/see/see-dataset.git")
        self.assertEqual(candidates[0]["tagVersion"], "master")
        self.assertEqual(candidates[0]["versions"], ["master", "release-2.0"])

    def test_build_related_code_module_candidates_reads_top_level_repo_fields(self):
        module = load_client_module()
        candidates = module.build_related_code_module_candidates(
            [
                {
                    "module_id": 252,
                    "module_name": "see-task",
                    "branch_address": "https://code.in.wezhuiyi.com/see/see-task.git",
                    "tag_version": "v2.10.1-rc54",
                },
            ],
            primary_module_id="246",
            branch_versions={
                "https://code.in.wezhuiyi.com/see/see-task.git": ["master", "v2.10.1-rc54"],
            },
            suggested_modules=[{
                "moduleName": "see-task",
                "role": "upstream",
            }],
        )

        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0]["repositoryAvailable"])
        self.assertEqual(candidates[0]["branchAddress"], "https://code.in.wezhuiyi.com/see/see-task.git")
        self.assertEqual(candidates[0]["versions"], ["v2.10.1-rc54", "master"])

    def test_build_related_code_module_candidates_ignores_once_without_repo_match(self):
        module = load_client_module()
        candidates = module.build_related_code_module_candidates(
            [{"module_id": 246, "module_name": "manifest", "branch": {"branch_address": "git://manifest", "tag_version": "v1"}}],
            primary_module_id="246",
            suggested_modules=[
                {"moduleName": "once", "role": "upstream"},
                {"moduleName": "asr", "role": "downstream"},
            ],
        )

        self.assertEqual([candidate["moduleName"] for candidate in candidates], ["asr"])

    def test_build_related_code_module_candidates_excludes_primary_by_repo_and_name(self):
        module = load_client_module()
        candidates = module.build_related_code_module_candidates(
            [
                {
                    "module_id": 252,
                    "module_name": "see-task",
                    "branch": {"branch_address": "https://code.in.wezhuiyi.com/see/see-task.git", "tag_version": "master"},
                },
                {
                    "module_id": 253,
                    "module_name": "see-dataset",
                    "branch": {"branch_address": "https://code.in.wezhuiyi.com/see/see-dataset.git", "tag_version": "master"},
                },
            ],
            primary_module_id="246",
            primary_branch_address="https://code.in.wezhuiyi.com/see/see-task.git",
            primary_module_name="see-task",
            suggested_modules=[
                {"moduleName": "see-task", "role": "upstream"},
                {"moduleName": "see-dataset", "role": "downstream"},
            ],
        )

        self.assertEqual([candidate["moduleName"] for candidate in candidates], ["see-dataset"])

    def test_related_code_dialog_applies_synced_versions_per_row(self):
        module = load_client_module()

        class Var:
            def __init__(self, value=""):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        class Combo:
            def __init__(self):
                self.values = []

            def configure(self, **kwargs):
                if "values" in kwargs:
                    self.values = list(kwargs["values"])

        class Button:
            def __init__(self):
                self.state = None

            def configure(self, **kwargs):
                self.state = kwargs.get("state", self.state)

        dialog = module.RelatedCodeVersionDialog.__new__(module.RelatedCodeVersionDialog)
        dialog.sync_button = Button()
        dialog.window = None
        original_showinfo = module.messagebox.showinfo
        original_showwarning = module.messagebox.showwarning
        module.messagebox.showinfo = lambda *args, **kwargs: None
        module.messagebox.showwarning = lambda *args, **kwargs: None
        row_a = {
            "candidate": {"moduleName": "see-task"},
            "version_var": Var("master"),
            "version_combo": Combo(),
        }
        row_b = {
            "candidate": {"moduleName": "see-dataset"},
            "version_var": Var("master"),
            "version_combo": Combo(),
        }

        try:
            dialog._apply_synced_versions([
                (row_a, "git://see-task", ["task-release", "master"], ""),
                (row_b, "git://see-dataset", ["dataset-release", "master"], ""),
            ])
        finally:
            module.messagebox.showinfo = original_showinfo
            module.messagebox.showwarning = original_showwarning

        self.assertEqual(row_a["version_combo"].values, ["task-release", "master"])
        self.assertEqual(row_b["version_combo"].values, ["dataset-release", "master"])
        self.assertEqual(row_a["version_var"].get(), "master")
        self.assertEqual(row_b["version_var"].get(), "master")

    def test_related_match_modules_queries_needed_names_without_scanning_all_products(self):
        module = load_client_module()

        class Client:
            def __init__(self):
                self.product_calls = 0
                self.search_names = []

            def get_products(self):
                self.product_calls += 1
                return []

            def get_modules_by_product(self, product_id):
                raise AssertionError("上下游匹配不应该扫描所有产品模块")

            def search_modules_by_names(self, names):
                self.search_names.append(list(names))
                return [{"module_id": 252, "module_name": "see-task", "branch": {"branch_address": "https://code.in.wezhuiyi.com/see/see-task.git", "tag_version": "master"}}]

        window = module.LogAnalyzerWindow.__new__(module.LogAnalyzerWindow)
        window.products = []
        window.modules = [{"module_id": 246, "module_name": "manifest", "branch": {"branch_address": "git://manifest", "tag_version": "v1"}}]
        window.all_modules = []
        window.all_modules_loaded = False
        window.branch_versions = {}

        client = Client()
        match_modules = window._get_related_match_modules(client, [{"moduleName": "see-task", "role": "upstream"}])
        candidates = module.build_related_code_module_candidates(
            match_modules,
            primary_module_id="246",
            branch_versions=window.branch_versions,
            suggested_modules=[{"moduleName": "see-task", "role": "upstream"}],
        )

        self.assertEqual(candidates[0]["moduleName"], "see-task")
        self.assertTrue(candidates[0]["repositoryAvailable"])
        self.assertEqual(candidates[0]["branchAddress"], "https://code.in.wezhuiyi.com/see/see-task.git")
        self.assertEqual(client.product_calls, 0)
        self.assertEqual(client.search_names, [["see-task"]])

    def test_assess_chain_uses_cached_db_versions_without_remote_branch_refresh(self):
        module = load_client_module()

        class Value:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        class Client:
            def __init__(self):
                self.remote_calls = 0
                self.cached_calls = []

            def discover_related_modules(self, *args, **kwargs):
                return {
                    "requiresRelatedEvidence": True,
                    "imageOcr": {
                        "available": True,
                        "engine": "paddleocr",
                        "extracted_text": "ERROR downstream see-task request failed",
                        "lines": [],
                        "average_confidence": 0.97,
                        "warnings": [],
                    },
                    "issueCandidates": [{
                        "issueSummary": "downstream see-task error",
                        "relatedModules": [{"moduleName": "see-task", "role": "upstream"}],
                    }],
                }

            def get_remote_branches(self, *args, **kwargs):
                self.remote_calls += 1
                return ["release-1"]

            def get_cached_branches(self, repo_url):
                self.cached_calls.append(repo_url)
                return ["master", "release-1", "release-2"]

            def search_modules_by_names(self, names):
                return [{"module_id": 252, "module_name": "see-task", "branch": {"branch_address": "git://see-task", "tag_version": "master"}}]

        window = module.LogAnalyzerWindow.__new__(module.LogAnalyzerWindow)
        window.product_id = Value("46")
        window.module_id = Value("246")
        window.branch_address = Value("git://manifest")
        window.tag_version = Value("v1")
        window.input_mode = Value("file")
        window.progress_percent = Value(22)
        window.upload_result = {"file_path": "/data/upload/demo.log"}
        window.modules = [{"module_id": 246, "module_name": "manifest", "branch": {"branch_address": "git://manifest", "tag_version": "v1"}}]
        window.all_modules = []
        window.all_modules_loaded = False
        window.branch_versions = {}
        window._set_status = lambda *args, **kwargs: None
        window._set_progress = lambda *args, **kwargs: None
        window._raise_if_cancelled = lambda: None
        window._get_image_description = lambda: ""
        captured_candidates = []
        def select_cached_version(candidates, decision, client):
            captured_candidates.extend(candidates)
            return [{
                "moduleId": candidates[0]["moduleId"],
                "moduleName": candidates[0]["moduleName"],
                "role": candidates[0]["role"],
                "branchAddress": candidates[0]["branchAddress"],
                "tagVersion": "release-2",
            }]
        window._show_related_code_version_dialog = select_cached_version
        window.root = type("Root", (), {"after": lambda self, delay, func=None: func() if func else None})()

        client = Client()
        related_modules, _, _ = window._assess_chain_code_and_upload_evidence(client)

        self.assertEqual(client.remote_calls, 0)
        self.assertEqual(client.cached_calls, ["git://see-task"])
        self.assertEqual(captured_candidates[0]["versions"], ["master", "release-1", "release-2"])
        self.assertEqual(related_modules[0]["tagVersion"], "release-2")
        self.assertEqual(window.upload_result["image_ocr"]["engine"], "paddleocr")

    def test_assess_chain_warns_once_when_image_ocr_is_unavailable(self):
        module = load_client_module()

        class Value:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        class Client:
            def discover_related_modules(self, *args, **kwargs):
                return {
                    "status": "image_ocr_unavailable",
                    "requiresRelatedEvidence": False,
                    "chainAssessmentComplete": False,
                    "message": "本地图片文字识别不可用，无法在分析前判断上下游链路；将保留原图进入综合分析。",
                    "imageOcr": {
                        "available": False,
                        "engine": "paddleocr",
                        "extracted_text": "",
                        "lines": [],
                        "average_confidence": 0.0,
                        "warnings": ["OCR runtime missing"],
                    },
                }

        window = module.LogAnalyzerWindow.__new__(module.LogAnalyzerWindow)
        window.product_id = Value("46")
        window.module_id = Value("256")
        window.branch_address = Value("git://see-task")
        window.tag_version = Value("v1")
        window.input_mode = Value("image")
        window.progress_percent = Value(22)
        window.upload_result = {
            "file_path": "/data/upload/error.png",
            "source_type": "image",
            "file_paths": ["/data/upload/error.png"],
        }
        window._set_status = lambda *args, **kwargs: None
        window._set_progress = lambda *args, **kwargs: None
        window._get_image_description = lambda: ""
        warnings = []
        window._show_info_message_async = lambda title, message: warnings.append((title, message))

        result = window._assess_chain_code_and_upload_evidence(Client())

        self.assertEqual(result, ([], [], []))
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0][0], "图片识别不可用")
        self.assertIn("无法在分析前判断上下游链路", warnings[0][1])
        self.assertFalse(window.upload_result["image_ocr"]["available"])

    def test_dedupe_related_modules_keeps_unique_version_roles(self):
        module = load_client_module()
        deduped = module.dedupe_related_modules([
            {"moduleId": "2", "moduleName": "asr", "role": "downstream", "branchAddress": "git://asr", "tagVersion": "v1"},
            {"moduleId": "2", "moduleName": "asr", "role": "downstream", "branchAddress": "git://asr", "tagVersion": "v1"},
            {"moduleId": "2", "moduleName": "asr", "role": "upstream", "branchAddress": "git://asr", "tagVersion": "v1"},
        ])

        self.assertEqual(len(deduped), 2)

    def test_builds_analysis_sections_for_popup_navigation_and_code_blocks(self):
        module = load_client_module()
        payload = {
            "task_id": "task-123",
            "repo_path": "/tmp/jira-automation-repos/task-123/repo-master",
            "knowledge_hit": True,
            "knowledge_hit_count": 2,
            "issue_conclusion": {
                "issue_category_label": "\u7f51\u7edc\u95ee\u9898",
                "conclusion_summary": "Redis connection was reset.",
                "root_cause": "Broker closed the socket.",
                "solution": "Check Redis keepalive.",
                "query_commands": ["redis-cli -h 127.0.0.1 -p 6379 ping"],
                "fix_commands": ["redis-cli CONFIG SET timeout 300"],
                "confidence": 0.82,
                "evidence": ["Connection reset by peer"],
            },
            "log_analysis": "Broken pipe usually means the client closed the connection.",
            "code_analysis": "Check streaming response handling and client timeout settings.",
            "analysis_evidence": {
                "used_code_context": True,
                "error_info_count": 1,
                "resolved_file_count": 1,
                "code_snippet_count": 1,
                "code_snippet_files": ["/repo/src/main/java/demo/Controller.java"],
            },
            "image_analysis": {
                "image_tag": "business_image",
                "summary": "椤甸潰鎻愮ず Redis 杩炴帴寮傚父",
                "extracted_text": "Redis connection reset by peer",
                "scene_summary": "\u7528\u6237\u70b9\u51fb\u4fdd\u5b58\u540e\u9875\u9762\u62a5\u9519",
                "missing_context": [
                    {
                        "direction": "upstream",
                        "title": "缂哄皯涓婃父璇锋眰淇℃伅",
                        "needed": ["璇锋眰鍙傛暟"],
                        "how_to_get": ["F12 Network 瀵煎嚭璇锋眰"],
                    }
                ],
            },
            "code_snippets": [
                {
                    "file": "/repo/src/main/java/demo/Controller.java",
                    "line": 42,
                    "numbered_snippet": "     41 | prepare();\n>>   42 | return response;",
                    "snippet": "return response;",
                }
            ],
            "code_findings": [
                {
                    "file": "/repo/src/main/java/demo/Controller.java",
                    "line": 42,
                    "reason": "\u65e5\u5fd7\u5806\u6808\u5b9a\u4f4d\u5230 Controller.java \u7b2c 42 \u884c\u3002",
                    "code": "     41 | prepare();\n>>   42 | return response;",
                }
            ],
        }

        sections = module.build_analysis_sections(payload)

        self.assertIn("return response;", payload["code_findings"][0]["code"])
        image_section = sections[2]
        self.assertEqual(image_section["title"], "\u56fe\u7247/\u4e1a\u52a1\u8bc6\u522b\u6458\u8981")
        self.assertIn("\u7528\u6237\u70b9\u51fb\u4fdd\u5b58\u540e\u9875\u9762\u62a5\u9519", image_section["content"])
        self.assertIn("缂哄皯涓婃父璇锋眰淇℃伅", image_section["content"])
        self.assertIn("Redis connection reset by peer", image_section["content"])
        finding_section = sections[3]
        self.assertEqual(finding_section["kind"], "code_finding_list")
        self.assertEqual(finding_section["items"][0]["file"], "/repo/src/main/java/demo/Controller.java")
        self.assertEqual(finding_section["items"][0]["line"], 42)
        self.assertIn("return response;", finding_section["items"][0]["code"])
        command_section = sections[4]
        self.assertEqual(command_section["title"], "\u6392\u67e5\u547d\u4ee4")
        self.assertIn("redis-cli -h 127.0.0.1 -p 6379 ping", command_section["content"])
        fix_section = sections[5]
        self.assertEqual(fix_section["title"], "\u4fee\u590d\u547d\u4ee4")
        self.assertIn("redis-cli CONFIG SET timeout 300", fix_section["content"])
        code_section = sections[8]
        self.assertEqual(code_section["kind"], "code_list")
        self.assertEqual(code_section["items"][0]["file"], "/repo/src/main/java/demo/Controller.java")
        self.assertEqual(code_section["items"][0]["line"], 42)
        self.assertEqual(code_section["items"][0]["content"], "return response;")

    def test_analysis_sections_repair_mojibake_category_labels(self):
        module = load_client_module()
        payload = {
            "issue_conclusion": {
                "issue_category": "network_issue",
                "issue_category_label": "\u7f51\u7edc\u95ee\u9898",
                "confidence": 0.73,
            },
        }

        sections = module.build_analysis_sections(payload)
        content = sections[0]["content"]

        self.assertIn("\u95ee\u9898\u5206\u7c7b: \u7f51\u7edc\u95ee\u9898", content)
        self.assertNotIn("\u7f51\u7edc?", content)

    def test_analysis_result_window_static_labels_are_readable_chinese(self):
        module = load_client_module()
        payload = {
            "issue_conclusion": {
                "issue_category_label": "\u4ee3\u7801\u95ee\u9898",
                "confidence": 0.8,
            },
        }
        root = tk.Tk()
        root.withdraw()
        try:
            popup = module.AnalysisResultWindow(root, payload)
            nav_titles = [popup.nav_list.get(index) for index in range(popup.nav_list.size())]
            text = popup.content_text.get("1.0", tk.END)

            self.assertEqual(popup.window.title(), "\u5206\u6790\u7ed3\u679c\u8be6\u60c5")
            self.assertIn("\u7ed3\u8bba", nav_titles)
            self.assertIn("\u95ee\u9898\u5206\u7c7b: \u4ee3\u7801\u95ee\u9898", text)
            self.assertNotIn("\u4e71\u7801", popup.window.title())
            self.assertNotIn("娴狅絿鐖滈梻", text)
        finally:
            root.destroy()

    def test_builds_short_analysis_summary_for_main_window(self):
        module = load_client_module()
        payload = {
            "task_id": "task-123",
            "knowledge_hit": True,
            "issue_conclusion": {
                "issue_category_label": "\u914d\u7f6e\u95ee\u9898",
                "conclusion_summary": "Config is invalid.",
                "confidence": 0.9,
            },
            "analysis_evidence": {
                "used_code_context": True,
                "error_info_count": 2,
                "resolved_file_count": 1,
                "code_snippet_count": 3,
            },
        }

        summary = module.build_analysis_summary(payload)

        self.assertIn("task-123", summary)
        self.assertIn("3", summary)
        self.assertIn("1", summary)
        self.assertTrue(summary.strip())

    def test_analysis_result_window_renders_navigation_titles_and_code_location(self):
        module = load_client_module()
        payload = {
            "log_analysis": "Log issue",
            "code_analysis": "Code issue",
            "analysis_evidence": {
                "used_code_context": True,
                "error_info_count": 1,
                "resolved_file_count": 1,
                "code_snippet_count": 1,
            },
            "code_snippets": [
                {
                    "file": "/repo/src/main/java/demo/Controller.java",
                    "line": 42,
                    "snippet": "return response;",
                }
            ],
        }
        root = tk.Tk()
        root.withdraw()
        try:
            popup = module.AnalysisResultWindow(root, payload)
            nav_titles = [popup.nav_list.get(index) for index in range(popup.nav_list.size())]
            text = popup.content_text.get("1.0", tk.END)

            self.assertGreaterEqual(len(nav_titles), 2)
            self.assertTrue(any(title for title in nav_titles))
            self.assertIn("Controller.java:42", text)
            self.assertIn("return response;", text)
        finally:
            root.destroy()

    def test_analysis_result_window_includes_markdown_subheadings_in_navigation(self):
        module = load_client_module()
        payload = {
            "code_analysis": "\n".join([
                "## \u6839\u56e0\u5224\u65ad",
                "\u8fd9\u91cc\u662f\u6839\u56e0",
                "### \u5904\u7406\u5efa\u8bae",
                "\u8fd9\u91cc\u662f\u5efa\u8bae",
            ]),
            "log_analysis": "# \u65e5\u5fd7\u73b0\u8c61\n\u8fd9\u91cc\u662f\u73b0\u8c61",
        }
        root = tk.Tk()
        root.withdraw()
        try:
            popup = module.AnalysisResultWindow(root, payload)
            nav_titles = [popup.nav_list.get(index) for index in range(popup.nav_list.size())]

            self.assertIn("  \u6839\u56e0\u5224\u65ad", nav_titles)
            self.assertIn("    \u5904\u7406\u5efa\u8bae", nav_titles)
            self.assertIn("  \u65e5\u5fd7\u73b0\u8c61", nav_titles)
        finally:
            root.destroy()

    def test_analysis_result_window_nav_selection_calls_see_with_selected_mark(self):
        module = load_client_module()
        payload = {
            "code_analysis": "## \u6839\u56e0\u5224\u65ad\n" + "\n".join(f"line {index}" for index in range(80)),
            "log_analysis": "## \u65e5\u5fd7\u73b0\u8c61\nlog body",
        }
        root = tk.Tk()
        root.withdraw()
        try:
            popup = module.AnalysisResultWindow(root, payload)
            nav_titles = [popup.nav_list.get(index) for index in range(popup.nav_list.size())]
            target_index = nav_titles.index("  \u65e5\u5fd7\u73b0\u8c61")
            seen_marks = []
            popup.content_text.see = seen_marks.append

            popup.nav_list.selection_clear(0, tk.END)
            popup.nav_list.selection_set(target_index)
            popup._on_nav_selected()

            self.assertEqual(seen_marks, [popup.nav_entries[target_index]["mark"]])
        finally:
            root.destroy()

    def test_formats_analysis_result_as_readable_sections_instead_of_raw_json(self):
        module = load_client_module()
        payload = {
            "task_id": "task-123",
            "repo_path": "/tmp/jira-automation-repos/task-123/repo-master",
            "log_analysis": "Broken pipe usually means the client closed the connection.",
            "code_analysis": "Check streaming response handling and client timeout settings.",
            "analysis_evidence": {
                "used_code_context": True,
                "error_info_count": 1,
                "resolved_file_count": 1,
                "code_snippet_count": 1,
                "code_snippet_files": ["/repo/src/main/java/demo/Controller.java"],
            },
            "code_snippets": [
                {
                    "file": "/repo/src/main/java/demo/Controller.java",
                    "line": 42,
                    "snippet": "return response;",
                }
            ],
        }

        formatted = module.format_result_payload("\u5206\u6790\u7ed3\u679c", payload)

        self.assertIn("\u5206\u6790\u7ed3\u679c", formatted)
        self.assertIn("\u95ee\u9898\u7ed3\u8bba", formatted)
        self.assertIn("\u65e5\u5fd7\u5206\u6790", formatted)
        self.assertIn("Controller.java:42", formatted)
        self.assertIn("1", formatted)
        self.assertIn("Controller.java:42", formatted)
        self.assertIn("return response;", formatted)
        self.assertNotIn("```", formatted)
        self.assertNotIn("###", formatted)
        self.assertIn("task-123", formatted)
        self.assertNotIn("{\n", formatted)

    def test_builds_analysis_result_html_export_with_escaped_content(self):
        module = load_client_module()
        payload = {
            "task_id": "task-123",
            "code_analysis": "Root cause contains <b>unsafe</b> markup.",
            "code_snippets": [
                {
                    "file": "/repo/app.py",
                    "line": 12,
                    "snippet": "<script>alert(1)</script>",
                }
            ],
        }

        html = module.build_result_html_document("\u5206\u6790\u7ed3\u679c", payload)

        self.assertIn("<!doctype html>", html)
        self.assertIn("report-shell", html)
        self.assertIn("report-toc", html)
        self.assertIn("executive-summary", html)
        self.assertIn("analysis-card", html)
        self.assertIn("\u5206\u6790\u7ed3\u679c", html)
        self.assertIn("task-123", html)
        self.assertIn("/repo/app.py:12", html)
        self.assertIn("&lt;b&gt;unsafe&lt;/b&gt;", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_builds_problem_oriented_sections_with_issue_code_evidence(self):
        module = load_client_module()
        payload = {
            "task_id": "task-123",
            "issue_conclusion": {
                "issue_category_label": "依赖/第三方服务问题",
                "issue_count": 2,
                "issues": [
                    {
                        "title": "问题1：ASR 音频下载失败",
                        "summary": "ASR 无法下载 MinIO 音频。",
                        "root_cause": "MinIO URL 不可访问。",
                        "solution": "检查对象是否存在以及 bucket 权限。",
                        "evidence": ["line 23 SeeTaskException", "line 88 Can not download file"],
                        "query_commands": ["grep -n 'Can not download file' app.log"],
                        "fix_commands": ["mc stat minio/zhuiyi-see/mock/audio.wav"],
                        "code_locations": [
                            {"file": "/repo/BaseAsrTransferService.java", "line": 226}
                        ],
                    },
                    {
                        "title": "回调日志误判为成功",
                        "summary": "失败链路仍打印 callback handle success。",
                        "evidence": ["line 44 callback handle success"],
                        "code_locations": [
                            {"file": "/repo/AsrTransformController.java", "line": 44}
                        ],
                    },
                ],
            },
            "analysis_evidence": {
                "used_code_context": True,
                "log_error_event_count": 2,
                "error_info_count": 1,
                "resolved_file_count": 2,
                "code_snippet_count": 2,
            },
            "code_findings": [
                {
                    "file": "/repo/BaseAsrTransferService.java",
                    "line": 226,
                    "reason": "回调处理 ASR 失败结果",
                    "code": ">>  226 | handleCallback(result);",
                },
                {
                    "file": "/repo/AsrTransformController.java",
                    "line": 44,
                    "reason": "回调入口打印成功日志",
                    "code": ">>   44 | log.info(\"callback handle success\");",
                },
            ],
        }

        sections = module.build_analysis_sections(payload)
        html = module.build_result_html_document("分析结果", payload)

        issue_section = next(section for section in sections if section["kind"] == "issue_list")
        self.assertEqual(issue_section["title"], "问题明细")
        self.assertIn("结论", [section["title"] for section in sections])
        self.assertEqual(len(issue_section["items"]), 2)
        self.assertEqual(issue_section["items"][0]["code_items"][0]["file"], "/repo/BaseAsrTransferService.java")
        self.assertIn("问题1", html)
        self.assertIn("ASR 音频下载失败", html)
        self.assertIn("分析依据", html)
        self.assertIn("修复建议", html)
        self.assertIn("修复命令", html)
        self.assertIn("BaseAsrTransferService.java:226", html)
        self.assertIn("handleCallback(result)", html)
        self.assertIn("问题2", html)

    def test_html_report_nests_structured_issues_under_problem_conclusion(self):
        module = load_client_module()
        raw_model_json = json.dumps({
            "issues": [{
                "title": "ASR 音频下载失败",
                "query_commands": ["grep -n 'download failed' app.log"],
            }]
        }, ensure_ascii=False, indent=2)
        payload = {
            "code_analysis": raw_model_json,
            "issue_conclusion": {
                "conclusion_summary": "日志中识别到两个相互独立的问题。",
                "issues": [
                    {
                        "title": "问题1：ASR 音频下载失败",
                        "issue_category_label": "下游依赖异常",
                        "confidence": 0.84,
                        "summary": "ASR 无法下载 MinIO 音频。",
                        "root_cause": "对象不存在或访问链路不可达。",
                        "evidence": ["line 24: Can not download file"],
                        "query_commands": ["grep -n 'download failed' app.log"],
                        "solution": "检查对象、权限和网络。",
                        "fix_commands": ["mc stat minio/audio.wav"],
                    },
                    {
                        "title": "投诉分析空指针",
                        "issue_category_label": "代码缺陷",
                        "confidence": 0.92,
                        "summary": "系统提示词为空时发生空指针。",
                        "root_cause": "返回值缺少空值保护。",
                    },
                ],
            },
            "analysis_evidence": {
                "log_error_event_count": 13,
                "grouped_issue_count": 2,
                "used_code_context": True,
                "used_related_code_context": True,
            },
        }

        sections = module.build_analysis_sections(payload)
        html = module.build_result_html_document("分析结果", payload)

        issue_section = next(section for section in sections if section["kind"] == "issue_list")
        self.assertEqual(issue_section["title"], "问题明细")
        self.assertIn("结论", [section["title"] for section in sections])
        self.assertEqual(issue_section["overview"], "日志中识别到两个相互独立的问题。")
        self.assertEqual(issue_section["items"][0]["title"], "ASR 音频下载失败")
        self.assertEqual(module._build_html_report_summary(payload)["error_count"], "2")
        self.assertEqual(module._build_html_report_summary(payload)["used_code"], "已结合上下游代码")
        self.assertNotIn(raw_model_json, html)
        self.assertNotIn('&quot;issues&quot;', html)
        self.assertIn('class="issue-nav"', html)
        self.assertIn('href="#issue-1"', html)
        self.assertIn('id="issue-2"', html)
        self.assertIn('class="issue-card__header"', html)
        self.assertIn('class="diagnostic-grid"', html)
        self.assertIn('class="command-panel command-panel--query"', html)
        self.assertIn('排查命令', html)
        self.assertIn('修复命令', html)
        self.assertIn('84%', html)
        self.assertNotIn('问题1 · 问题1', html)
        self.assertIn('href="#issue-1-root-cause"', html)
        self.assertIn('href="#issue-1-evidence"', html)
        self.assertIn('id="issue-1-solution"', html)

    def test_analysis_result_window_renders_issue_details_with_three_level_navigation(self):
        module = load_client_module()
        payload = {
            "issue_conclusion": {
                "conclusion_summary": "总体结论",
                "issues": [{
                    "title": "ASR 音频下载失败",
                    "summary": "对象下载失败。",
                    "root_cause": "对象不存在或网络不可达。",
                    "evidence": ["日志行 24: Can not download file"],
                    "solution": "检查对象和网络。",
                    "query_commands": ["mc stat bucket/audio.wav"],
                    "fix_commands": ["重新上传 audio.wav"],
                    "code_locations": [{"file": "BaseAsrTransferService.java", "line": 226, "reason": "失败入口"}],
                }],
            },
        }
        root = tk.Tk()
        root.withdraw()
        try:
            popup = module.AnalysisResultWindow(root, payload)
            nav_titles = [popup.nav_list.get(index) for index in range(popup.nav_list.size())]
            text = popup.content_text.get("1.0", tk.END)

            self.assertIn("问题明细", nav_titles)
            self.assertIn("  问题1 · ASR 音频下载失败", nav_titles)
            self.assertIn("    现象摘要", nav_titles)
            self.assertIn("    根因判断", nav_titles)
            self.assertIn("    分析依据", nav_titles)
            self.assertIn("    修复建议", nav_titles)
            self.assertIn("    排查命令", nav_titles)
            self.assertIn("    修复命令", nav_titles)
            self.assertIn("    相关代码", nav_titles)
            self.assertIn("对象不存在或网络不可达", text)
            self.assertIn("BaseAsrTransferService.java:226", text)
        finally:
            root.destroy()

    def test_progress_frame_is_built_before_the_expandable_image_form(self):
        module = load_client_module()
        source = inspect.getsource(module.LogAnalyzerWindow._build_layout)

        self.assertLess(source.index("progress_frame ="), source.index("form ="))

    def test_issue_sections_append_unexpanded_log_error_events(self):
        module = load_client_module()
        payload = {
            "issue_conclusion": {
                "issue_category_label": "依赖/第三方服务问题",
                "issues": [
                    {
                        "title": "ASR 音频下载失败",
                        "summary": "ASR 无法下载 MinIO 音频。",
                        "evidence": ["SeeTaskException", "BaseAsrTransferService.java:226"],
                    }
                ],
            },
            "analysis_evidence": {
                "log_error_event_count": 2,
                "log_error_events": [
                    {
                        "index": 1,
                        "line": 23,
                        "text": "com.zhuiyi.see.task.exception.SeeTaskException: Can not download file\n    at com.zhuiyi.see.task.service.asr.BaseAsrTransferService.handleCallback(BaseAsrTransferService.java:226)",
                    },
                    {
                        "index": 2,
                        "line": 5261,
                        "text": "java.lang.NullPointerException: null\n    at com.zhuiyi.see.task.service.impl.ComplaintAnalysisService.doAnalyze(ComplaintAnalysisService.java:143)",
                    },
                ],
            },
        }

        sections = module.build_analysis_sections(payload)
        html = module.build_result_html_document("分析结果", payload)

        issue_section = next(section for section in sections if section["kind"] == "issue_list")
        self.assertEqual(len(issue_section["items"]), 2)
        self.assertIn("NullPointerException", issue_section["items"][1]["title"])
        self.assertIn("ComplaintAnalysisService.java:143", html)
        self.assertIn("问题2", html)

    def test_issue_sections_use_grouped_errors_without_duplicate_fallback_issues(self):
        module = load_client_module()
        asr_text = "SeeTaskException: Can not download file\n    at demo.Asr.run(Asr.java:10)"
        npe_text = "java.lang.NullPointerException: null\n    at demo.Complaint.run(Complaint.java:42)"
        payload = {
            "issue_conclusion": {
                "issues": [{
                    "title": "ASR download failed",
                    "summary": "Can not download file",
                    "evidence": [asr_text],
                }],
            },
            "analysis_evidence": {
                "log_error_event_count": 4,
                "log_error_events": [
                    {"line": 10, "text": asr_text},
                    {"line": 20, "text": asr_text},
                    {"line": 30, "text": asr_text},
                    {"line": 42, "text": npe_text},
                ],
                "grouped_issue_count": 2,
                "grouped_log_errors": [
                    {
                        "first_line": 10,
                        "last_line": 30,
                        "occurrence_count": 3,
                        "languages": ["java"],
                        "representative_text": asr_text,
                    },
                    {
                        "first_line": 42,
                        "last_line": 42,
                        "occurrence_count": 1,
                        "languages": ["java"],
                        "representative_text": npe_text,
                    },
                ],
            },
        }

        issue_section = next(
            section for section in module.build_analysis_sections(payload)
            if section["kind"] == "issue_list"
        )

        self.assertEqual(len(issue_section["items"]), 2)
        self.assertIn("NullPointerException", issue_section["items"][1]["title"])
        self.assertEqual(issue_section["items"][1]["occurrence_count"], 1)
        self.assertEqual(issue_section["items"][1]["language"], "java")

    def test_issue_sections_recover_alias_issues_from_raw_code_analysis(self):
        module = load_client_module()
        payload = {
            "code_analysis": json.dumps({
                "conclusion_summary": "识别到两个问题",
                "issue_details": [
                    {
                        "title": "依赖下载失败",
                        "issue_category": "dependency_issue",
                        "summary": "依赖包下载异常",
                        "fix_commond": "pip install demo-package",
                    },
                    {
                        "title": "服务连接失败",
                        "summary": "目标服务拒绝连接",
                        "query_command": ["curl -v http://service/health"],
                    },
                ],
            }, ensure_ascii=False),
            "issue_conclusion": {
                "conclusion_summary": "识别到两个问题",
                "issues": [],
            },
        }

        sections = module.build_analysis_sections(payload)
        issue_section = next(section for section in sections if section["kind"] == "issue_list")
        section_titles = [section["title"] for section in sections]
        rendered = module.build_result_html_document("分析结果", payload)

        self.assertEqual(len(issue_section["items"]), 2)
        self.assertEqual(issue_section["items"][0]["fix_commands"], ["pip install demo-package"])
        self.assertEqual(issue_section["items"][1]["query_commands"], ["curl -v http://service/health"])
        self.assertNotIn("问题结论", section_titles)
        self.assertNotIn("fix_commond", rendered)
        self.assertNotIn("issue_details", rendered)
        self.assertNotIn("dependency_issue", rendered)
        self.assertIn("依赖问题", rendered)

    def test_issue_sections_convert_top_level_ai_json_to_chinese_detail(self):
        module = load_client_module()
        payload = {
            "code_analysis": json.dumps({
                "issue_category": "network_issue",
                "conclusion_summary": "服务健康检查失败",
                "root_cause": "服务地址不可达",
                "solution": "核对服务地址和网络策略",
                "query_commands": ["curl -v http://service/health"],
                "fix_commands": ["kubectl rollout restart deployment/demo"],
                "evidence": ["图片中显示 connection refused"],
            }, ensure_ascii=False),
            "issue_conclusion": {},
        }

        sections = module.build_analysis_sections(payload)
        issue_section = next(section for section in sections if section["kind"] == "issue_list")
        rendered = module.build_result_html_document("分析结果", payload)

        self.assertEqual(len(issue_section["items"]), 1)
        self.assertEqual(issue_section["items"][0]["title"], "服务健康检查失败")
        self.assertEqual(issue_section["items"][0]["fix_commands"], ["kubectl rollout restart deployment/demo"])
        self.assertNotIn('"fix_commands"', rendered)
        self.assertNotIn('"evidence"', rendered)
        self.assertIn("网络问题", rendered)

    def test_html_issue_header_uses_number_and_wide_title_columns(self):
        module = load_client_module()
        payload = {
            "issue_conclusion": {
                "issues": [{
                    "title": "离线 ASR 回调失败，ASR 无法下载 MinIO 音频文件",
                    "issue_category_label": "依赖问题",
                    "confidence": 0.86,
                }]
            }
        }

        rendered = module.build_result_html_document("分析结果", payload)

        self.assertIn('<div class="issue-number">01</div>', rendered)
        self.assertIn("grid-template-columns: 48px minmax(0, 1fr);", rendered)
        self.assertNotIn("grid-template-columns: 48px minmax(0, 1fr) auto;", rendered)

    def test_grouped_error_fallback_checks_every_error_instead_of_stopping_by_count(self):
        module = load_client_module()
        first_error = "SeeTaskException: Can not download file"
        second_error = "java.lang.NullPointerException: null"
        payload = {
            "issue_conclusion": {
                "issues": [{
                    "title": "综合问题",
                    "summary": "需要继续排查",
                }],
            },
            "analysis_evidence": {
                "grouped_log_errors": [
                    {"first_line": 10, "representative_text": first_error},
                    {"first_line": 42, "representative_text": second_error},
                ],
            },
        }

        issue_section = next(
            section for section in module.build_analysis_sections(payload)
            if section["kind"] == "issue_list"
        )

        rendered_issues = "\n".join(
            f"{item.get('title', '')}\n{item.get('summary', '')}\n{item.get('evidence', '')}"
            for item in issue_section["items"]
        )
        self.assertEqual(len(issue_section["items"]), 2)
        self.assertIn(first_error, rendered_issues)
        self.assertIn(second_error, rendered_issues)

    def test_extracts_code_locations_from_java_python_go_and_shell_events(self):
        module = load_client_module()
        event_text = """java.lang.NullPointerException: null
    at demo.Demo.run(Demo.java:42)
  File "trainer.py", line 18, in train
        /workspace/internal/runner.go:27 +0x12f
deploy.sh: line 9: kubectl: command not found
"""

        locations = module._extract_code_locations_from_log_event(event_text)

        self.assertEqual(
            {(item["file"], item["line"], item["language"]) for item in locations},
            {
                ("Demo.java", 42, "java"),
                ("trainer.py", 18, "python"),
                ("runner.go", 27, "go"),
                ("deploy.sh", 9, "shell"),
            },
        )

    def test_formats_go_code_snippets_with_readable_language_label(self):
        module = load_client_module()
        payload = {
            "code_analysis": "Go panic comes from a nil trainer runner.",
            "code_snippets": [
                {
                    "file": "/repo/internal/trainer/runner.go",
                    "line": 42,
                    "snippet": "return runner.Train(ctx)",
                    "module_name": "algorithm-platform",
                }
            ],
            "code_findings": [
                {
                    "file": "/repo/internal/trainer/runner.go",
                    "line": 42,
                    "code": ">>   42 | return runner.Train(ctx)",
                    "module_name": "algorithm-platform",
                }
            ],
        }

        sections = module.build_analysis_sections(payload)
        formatted = module.format_result_payload("\u5206\u6790\u7ed3\u679c", payload)
        code_items = next(section["items"] for section in sections if section["kind"] == "code_list")
        finding_items = next(section["items"] for section in sections if section["kind"] == "code_finding_list")

        self.assertEqual(code_items[0]["language"], "Go")
        self.assertEqual(finding_items[0]["language"], "Go")
        self.assertIn("[algorithm-platform] /repo/internal/trainer/runner.go:42  [Go]", formatted)

    def test_formats_analysis_result_warns_when_no_code_context_is_used(self):
        module = load_client_module()
        payload = {
            "log_analysis": "Only log analysis.",
            "code_analysis": "No code files were available.",
            "analysis_evidence": {
                "used_code_context": False,
                "error_info_count": 1,
                "resolved_file_count": 0,
                "code_snippet_count": 0,
                "code_snippet_files": [],
            },
            "code_snippets": [],
        }

        formatted = module.format_result_payload("\u5206\u6790\u7ed3\u679c", payload)

        self.assertIn("No code files were available.", formatted)
        self.assertIn("0", formatted)

    def test_formats_upload_result_as_key_metrics(self):
        module = load_client_module()
        payload = {
            "message": "\u6587\u4ef6\u4e0a\u4f20\u5e76\u5904\u7406\u6210\u529f",
            "file_path": "/data/upload/demo.log",
            "date_filter_applied": True,
            "target_date": "2026-06-07",
            "original_line_count": 100,
            "filtered_line_count": 8,
            "matched_line_count": 2,
            "warning": "\u6307\u5b9a\u65e5\u671f\u6ca1\u6709\u5339\u914d\u5230\u65e5\u5fd7\u5185\u5bb9",
        }

        formatted = module.format_result_payload("\u4e0a\u4f20\u7ed3\u679c", payload)

        self.assertIn("\u4e0a\u4f20\u7ed3\u679c", formatted)
        self.assertIn("\u76ee\u6807\u65e5\u671f: 2026-06-07", formatted)
        self.assertIn("\u539f\u59cb\u884c\u6570: 100", formatted)
        self.assertIn("\u8fc7\u6ee4\u540e\u884c\u6570: 8", formatted)
        self.assertIn("\u63d0\u9192", formatted)
        self.assertNotIn('"file_path"', formatted)

    def test_window_static_text_uses_valid_chinese_labels(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)
            texts = [root.title(), window.status.get()]

            def collect_text(widget):
                try:
                    text = widget.cget("text")
                except tk.TclError:
                    text = ""
                if text:
                    texts.append(text)
                for child in widget.winfo_children():
                    collect_text(child)

            collect_text(root)

            joined = "\n".join(texts)
            self.assertIn(module.APP_RELEASE_LABEL, joined)
            self.assertNotIn("UTF-8 Fix", joined)
            self.assertIn("\u4f7f\u7528\u65b9\u6cd5", joined)
            self.assertIn(module.DEFAULT_BACKEND_URL, joined)
            self.assertIn("\u5c39\u752b\u4e7e&\u5f20\u5c27", joined)
            self.assertIn("\u9690\u79c1\u6027\u8bf4\u660e", joined)
            self.assertIn("\u540c\u6b65 Git \u9879\u76ee", joined)
            self.assertIn("\u62c9\u53d6\u7248\u672c\u53f7", joined)
            self.assertIn("\u4e0a\u4f20\u65e5\u5fd7", joined)
            self.assertIn("\u5f00\u59cb\u5206\u6790", joined)
            self.assertNotIn("\u4e0a\u4f20\u5e76\u5206\u6790", joined)
            self.assertNotIn("\u91cd\u8bd5\u4e0a\u6b21\u64cd\u4f5c", joined)
            self.assertNotIn("\u4e2d\u65ad\u64cd\u4f5c", joined)
            self.assertIn("\u4ea7\u54c1", joined)
            self.assertIn("\u6a21\u5757", joined)
            self.assertEqual(window.backend_url.get(), module.DEFAULT_BACKEND_URL)
            self.assertEqual(window.date_filter.get(), "")
            self.assertNotIn("????", joined)
        finally:
            root.destroy()

    def test_window_comboboxes_allow_typing_to_filter_options(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)
            products = ["65 - pal", "66 - bot", "67 - palace"]

            window._set_combobox_values(window.product_combo, products)
            window.product_selection.set("pal")
            window._filter_combobox_values(window.product_combo)

            self.assertEqual(str(window.product_combo.cget("state")), "normal")
            self.assertEqual(list(window.product_combo["values"]), ["65 - pal", "67 - palace"])

            window.product_selection.set("")
            window._filter_combobox_values(window.product_combo)

            self.assertEqual(list(window.product_combo["values"]), products)
        finally:
            root.destroy()

    def test_window_switches_to_image_mode_and_exposes_image_fields(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)

            window.input_mode.set("image")
            window._on_input_mode_changed()
            root.update()

            self.assertEqual(window.path_label_var.get(), "\u56fe\u7247\u6587\u4ef6")
            self.assertEqual(str(window.date_combo.cget("state")), "disabled")
            self.assertTrue(window.image_tag_combo.winfo_ismapped())
            self.assertTrue(window.image_description_text.winfo_ismapped())
        finally:
            root.destroy()

    def test_primary_actions_stay_visible_before_image_details(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)

            window.input_mode.set("image")
            window._on_input_mode_changed()
            root.update_idletasks()

            action_frame = window.upload_button.master
            self.assertEqual(action_frame.winfo_manager(), "grid")
            self.assertIs(action_frame.master, window.image_description_text.master)
            self.assertLess(
                int(action_frame.grid_info()["row"]),
                int(window.image_description_text.grid_info()["row"]),
            )
            self.assertEqual(window.upload_button.winfo_manager(), "pack")
            self.assertEqual(window.analyze_button.winfo_manager(), "pack")
        finally:
            root.destroy()

    def test_image_mode_keeps_multiple_cached_images_with_delete_buttons(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)
            window.input_mode.set("image")
            window._on_input_mode_changed()

            window._add_image_paths(["C:/tmp/first.png", "C:/tmp/second.jpg"])
            first_path = str(Path("C:/tmp/first.png"))
            second_path = str(Path("C:/tmp/second.jpg"))
            self.assertEqual(window.image_paths, [first_path, second_path])
            self.assertIn("2", window.file_path.get())

            window._remove_image_path(first_path)
            self.assertEqual(window.image_paths, [second_path])
            self.assertIn("1", window.file_path.get())
        finally:
            root.destroy()

    def test_upload_log_posts_file_and_date_filter_to_remote_backend(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example/api/", session=session)

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(b"2026-06-07 ERROR boom")
            temp_path = temp_file.name

        result = client.upload_log(
            file_path=temp_path,
            product_id="1",
            module_id="2",
            branch_address="https://git.example/repo.git",
            tag_version="v1",
            date_filter="-3",
        )

        self.assertTrue(result["ok"])
        url, kwargs = session.posts[0]
        self.assertEqual(url, "http://server.example/api/logfile/upload")
        self.assertEqual(kwargs["data"]["product_id"], "1")
        self.assertEqual(kwargs["data"]["module_id"], "2")
        self.assertEqual(kwargs["data"]["address"], "https://git.example/repo.git")
        self.assertEqual(kwargs["data"]["tag_version"], "v1")
        self.assertEqual(kwargs["data"]["date_filter"], "-3")
        self.assertIn("file", kwargs["files"])

    def test_upload_image_posts_image_metadata_to_remote_backend(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example/api/", session=session)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_file:
            temp_file.write(b"fake-image")
            temp_path = temp_file.name

        result = client.upload_image(
            image_path=temp_path,
            product_id="1",
            module_id="2",
            branch_address="https://git.example/repo.git",
            tag_version="v1",
            image_tag="business_image",
            image_description="\u70b9\u51fb\u4fdd\u5b58\u65f6\u62a5\u9519",
        )

        self.assertTrue(result["ok"])
        url, kwargs = session.posts[0]
        self.assertEqual(url, "http://server.example/api/logfile/upload_image")
        self.assertEqual(kwargs["data"]["image_tag"], "business_image")
        self.assertEqual(kwargs["data"]["image_description"], "\u70b9\u51fb\u4fdd\u5b58\u65f6\u62a5\u9519")
        self.assertIn("file", kwargs["files"])

    def test_upload_images_posts_multiple_images_to_remote_backend(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example/api/", session=session)

        temp_paths = []
        for index in range(2):
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"-{index}.png") as temp_file:
                temp_file.write(f"fake-image-{index}".encode("utf-8"))
                temp_paths.append(temp_file.name)

        result = client.upload_images(
            image_paths=temp_paths,
            product_id="1",
            module_id="2",
            branch_address="https://git.example/repo.git",
            tag_version="v1",
            image_tag="business_image",
            image_description="\u7b2c\u4e00\u5f20\u662f\u67e5\u8be2\u6761\u4ef6\uff0c\u7b2c\u4e8c\u5f20\u662f\u4fdd\u5b58\u62a5\u9519",
        )

        self.assertTrue(result["ok"])
        url, kwargs = session.posts[0]
        self.assertEqual(url, "http://server.example/api/logfile/upload_image")
        self.assertEqual(kwargs["data"]["image_tag"], "business_image")
        self.assertEqual(kwargs["data"]["image_description"], "\u7b2c\u4e00\u5f20\u662f\u67e5\u8be2\u6761\u4ef6\uff0c\u7b2c\u4e8c\u5f20\u662f\u4fdd\u5b58\u62a5\u9519")
        self.assertEqual([item[0] for item in kwargs["files"]], ["files", "files"])
        self.assertEqual(len(kwargs["files"]), 2)

    def test_loads_products_from_backend_database_api(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        products = client.get_products()

        self.assertEqual(products, [{"id": 1, "name": "bot"}])
        self.assertEqual(session.gets[0], ("http://server.example/product/get", {}))

    def test_loads_modules_and_branch_options_for_selected_product(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        modules = client.get_modules_by_product("1")

        self.assertEqual(modules[0]["module_id"], 2)
        self.assertEqual(modules[0]["branch"]["branch_address"], "https://git.example/repo.git")
        self.assertEqual(session.gets[0], ("http://server.example/module/get", {"params": {"product_id": "1"}}))

    def test_module_switch_uses_cached_database_versions_without_remote_fetch(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)
            remote_calls = []
            window.load_remote_branches_for_selected_repo_async = lambda: remote_calls.append("called")
            window.modules = [{
                "module_id": 2,
                "module_name": "dialog",
                "branch": {
                    "branch_address": "https://git.example/repo.git",
                    "tag_version": "v1",
                },
            }]
            window.module_by_label = {
                window._module_label(window.modules[0]): window.modules[0],
            }
            window.branch_versions = {
                "https://git.example/repo.git": ["v1", "v2"],
            }
            window._set_combobox_values(window.tag_combo, ["v1", "v2"])
            window.module_selection.set("2 - dialog")

            window.on_module_selected()

            self.assertEqual(remote_calls, [])
            self.assertEqual(window.branch_address.get(), "https://git.example/repo.git")
            self.assertEqual(window.tag_version.get(), "v1")
            self.assertEqual(list(window.tag_combo["values"]), ["v1", "v2"])
        finally:
            root.destroy()

    def test_module_switch_does_not_restore_version_from_another_repo(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)
            window.load_remote_branches_for_selected_repo_async = lambda: None
            repository = "https://git.example/pal-quality-inspection.git"
            window.modules = [{
                "module_id": 251,
                "module_name": "pal-quality-inspection",
                "branch": {
                    "branch_address": repository,
                    "tag_version": "v2.10.1-rc54",
                },
            }]
            window.module_by_label = {
                window._module_label(window.modules[0]): window.modules[0],
            }
            window.branch_versions = {repository: ["master", "release-1.8"]}
            window.module_selection.set("251 - pal-quality-inspection")

            window.on_module_selected()

            self.assertEqual(window.branch_address.get(), repository)
            self.assertEqual(window.tag_version.get(), "master")
            self.assertNotEqual(window.tag_version.get(), "v2.10.1-rc54")
        finally:
            root.destroy()

    def test_form_buttons_are_next_to_their_related_fields(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)

            tag_grid = window.tag_combo.grid_info()
            version_button_grid = window.refresh_versions_button.grid_info()
            file_entry_grid = window.log_file_entry.grid_info()
            choose_file_grid = window.choose_file_button.grid_info()
            backend_entry_grid = window.backend_entry.grid_info()
            sync_button_grid = window.sync_git_button.grid_info()

            self.assertEqual(version_button_grid["row"], tag_grid["row"])
            self.assertEqual(int(version_button_grid["column"]), int(tag_grid["column"]) + 1)
            self.assertEqual(choose_file_grid["row"], file_entry_grid["row"])
            self.assertEqual(int(choose_file_grid["column"]), int(file_entry_grid["column"]) + 1)
            self.assertEqual(sync_button_grid["row"], backend_entry_grid["row"])
            self.assertEqual(int(sync_button_grid["column"]), int(backend_entry_grid["column"]) + 1)
        finally:
            root.destroy()

    def test_module_switch_fetches_remote_when_database_versions_are_missing(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)
            remote_calls = []
            window.load_remote_branches_for_selected_repo_async = lambda: remote_calls.append("called")
            window.modules = [{
                "module_id": 2,
                "module_name": "dialog",
                "branch": {
                    "branch_address": "https://git.example/repo.git",
                    "tag_version": "",
                },
            }]
            window.module_by_label = {
                window._module_label(window.modules[0]): window.modules[0],
            }
            window.branch_versions = {
                "https://git.example/repo.git": [],
            }
            window.module_selection.set("2 - dialog")

            window.on_module_selected()

            self.assertEqual(remote_calls, ["called"])
        finally:
            root.destroy()

    def test_module_switch_fetches_remote_when_database_only_has_default_version(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)
            remote_calls = []
            window.load_remote_branches_for_selected_repo_async = lambda force_refresh=False: remote_calls.append(force_refresh)
            window.modules = [{
                "module_id": 256,
                "module_name": "see-task",
                "branch": {
                    "branch_address": "https://code.in.wezhuiyi.com/see/see-task.git",
                    "tag_version": "master",
                },
            }]
            window.module_by_label = {
                window._module_label(window.modules[0]): window.modules[0],
            }
            window.branch_versions = {
                "https://code.in.wezhuiyi.com/see/see-task.git": ["master"],
            }
            window.module_selection.set("256 - see-task")

            window.on_module_selected()

            self.assertEqual(remote_calls, [False])
            self.assertEqual(window.branch_address.get(), "https://code.in.wezhuiyi.com/see/see-task.git")
            self.assertEqual(window.tag_version.get(), "master")
        finally:
            root.destroy()

    def test_manual_refresh_versions_button_forces_remote_refresh(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)
            remote_calls = []
            window.load_remote_branches_for_selected_repo_async = lambda force_refresh=False: remote_calls.append(force_refresh)

            window.refresh_branch_versions_async()

            self.assertEqual(remote_calls, [True])
        finally:
            root.destroy()

    def test_submits_async_analysis_task_after_upload(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        result = client.submit_analysis_task(
            product_id="1",
            module_id="2",
            branch_address="https://git.example/repo.git",
            tag_version="v1",
            file_path="/data/upload/log.txt",
            log_id=9,
        )

        self.assertEqual(result["ok"], True)
        url, kwargs = session.posts[0]
        self.assertEqual(url, "http://server.example/analysis/submit_async")
        self.assertEqual(kwargs["json"]["productId"], "1")
        self.assertEqual(kwargs["json"]["file_path"], "/data/upload/log.txt")
        self.assertEqual(kwargs["json"]["log_id"], 9)

    def test_submits_async_analysis_task_with_image_metadata_after_image_upload(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        result = client.submit_analysis_task(
            product_id="1",
            module_id="2",
            branch_address="https://git.example/repo.git",
            tag_version="v1",
            file_path="/data/upload/demo-image.png",
            log_id=9,
            source_type="image",
            image_tag="business_image",
            image_description="\u70b9\u51fb\u4fdd\u5b58\u65f6\u62a5\u9519",
        )

        self.assertEqual(result["ok"], True)
        url, kwargs = session.posts[0]
        self.assertEqual(url, "http://server.example/analysis/submit_async")
        self.assertEqual(kwargs["json"]["source_type"], "image")
        self.assertEqual(kwargs["json"]["image_tag"], "business_image")
        self.assertEqual(kwargs["json"]["image_description"], "\u70b9\u51fb\u4fdd\u5b58\u65f6\u62a5\u9519")

    def test_submits_async_analysis_task_with_reused_image_ocr(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)
        image_ocr = {
            "available": True,
            "engine": "paddleocr",
            "extracted_text": "java.lang.NullPointerException: null",
            "lines": [],
            "average_confidence": 0.96,
            "warnings": [],
        }

        client.submit_analysis_task(
            product_id="1",
            module_id="2",
            branch_address="https://git.example/repo.git",
            tag_version="v1",
            file_path="/data/upload/demo-image.png",
            source_type="image",
            image_tag="log_image",
            image_ocr=image_ocr,
        )

        _, kwargs = session.posts[0]
        self.assertEqual(kwargs["json"]["image_ocr"], image_ocr)

    def test_submits_async_analysis_task_with_multiple_image_paths(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        result = client.submit_analysis_task(
            product_id="1",
            module_id="2",
            branch_address="https://git.example/repo.git",
            tag_version="v1",
            file_path="/data/upload/screen-1.png",
            log_id=9,
            source_type="image",
            image_tag="business_image",
            image_description="鎸夐『搴忓垎鏋愪袱寮犲浘",
            file_paths=["/data/upload/screen-1.png", "/data/upload/screen-2.png"],
            log_ids=[9, 10],
        )

        self.assertEqual(result["ok"], True)
        url, kwargs = session.posts[0]
        self.assertEqual(url, "http://server.example/analysis/submit_async")
        self.assertEqual(kwargs["json"]["file_paths"], ["/data/upload/screen-1.png", "/data/upload/screen-2.png"])
        self.assertEqual(kwargs["json"]["log_ids"], [9, 10])

    def test_gets_async_task_status(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        status = client.get_task_status("task-123")

        self.assertTrue(status["ready"])
        self.assertEqual(status["result"]["code_analysis"], "done")
        self.assertEqual(session.gets[0], ("http://server.example/analysis/task/task-123", {}))

    def test_cancels_async_task(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        result = client.cancel_task("task-123")

        self.assertEqual(result["state"], "REVOKED")
        self.assertEqual(session.posts[0], ("http://server.example/analysis/task/task-123/cancel", {}))

    def test_loads_remote_branches_and_tags_for_selected_repo_url(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        branches = client.get_remote_branches("https://code.in.wezhuiyi.com/group/repo.git")

        self.assertEqual(
            branches,
            ["master", "feature/log-analyzer", "v1.1.0", "v5.136.7-ZYKJ20230046-rc1"],
        )
        self.assertEqual(
            session.gets[0],
            (
                "http://server.example/git/branches",
                {"params": {"repo_url": "https://code.in.wezhuiyi.com/group/repo.git"}},
            ),
        )

    def test_force_refresh_remote_branches_sends_refresh_flag(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        client.get_remote_branches("https://code.in.wezhuiyi.com/group/repo.git", force_refresh=True)

        self.assertEqual(
            session.gets[0],
            (
                "http://server.example/git/branches",
                {"params": {"repo_url": "https://code.in.wezhuiyi.com/group/repo.git", "refresh": "1"}},
            ),
        )

    def test_loads_cached_branches_without_triggering_remote_sync(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        versions = client.get_cached_branches("https://code.in.wezhuiyi.com/group/repo.git")

        self.assertIn("feature/log-analyzer", versions)
        self.assertEqual(
            session.gets[0],
            (
                "http://server.example/git/branches",
                {
                    "params": {
                        "repo_url": "https://code.in.wezhuiyi.com/group/repo.git",
                        "cached_only": "1",
                    }
                },
            ),
        )

    def test_syncs_git_projects_from_backend(self):
        module = load_client_module()
        session = FakeSession()
        client = module.LogAnalyzerApiClient("http://server.example", session=session)

        result = client.sync_git_projects()

        self.assertEqual(result["synced_projects"], 3)
        self.assertEqual(session.posts[0], ("http://server.example/git/sync-projects", {}))

    def test_polling_task_status_tolerates_temporary_connection_errors(self):
        module = load_client_module()

        class FlakyClient:
            def __init__(self):
                self.calls = 0

            def get_task_status(self, task_id):
                self.calls += 1
                if self.calls == 1:
                    raise requests.ConnectionError("connection reset")
                return {
                    "task_id": task_id,
                    "state": "SUCCESS",
                    "ready": True,
                    "successful": True,
                    "result": {"code_analysis": "done"},
                }

        statuses = []
        result = module.poll_task_until_ready(
            FlakyClient(),
            "task-123",
            on_status=statuses.append,
            sleep_func=lambda seconds: None,
        )

        self.assertEqual(result["code_analysis"], "done")
        self.assertIn("1/10", statuses[0])

    def test_polling_reports_progress_messages(self):
        module = load_client_module()

        class ProgressClient:
            def __init__(self):
                self.calls = 0

            def get_task_status(self, task_id):
                self.calls += 1
                if self.calls == 1:
                    return {
                        "task_id": task_id,
                        "state": "PROGRESS",
                        "ready": False,
                        "progress": {
                            "stage": "clone_repo_done",
                            "stage_label": "娴狅絿鐖滈幏澶婂絿",
                            "stage_percent": 100,
                            "percent": 45,
                            "message": "娴狅絿鐖滈幏澶婂絿 100%",
                        },
                    }
                return {
                    "task_id": task_id,
                    "state": "SUCCESS",
                    "ready": True,
                    "successful": True,
                    "result": {"code_analysis": "done"},
                }

        statuses = []
        progresses = []
        result = module.poll_task_until_ready(
            ProgressClient(),
            "task-123",
            on_status=statuses.append,
            on_progress=progresses.append,
            sleep_func=lambda seconds: None,
        )

        self.assertEqual(result["code_analysis"], "done")
        self.assertNotIn("娴狅絿鐖滈幏澶婂絿 100%", statuses)
        self.assertEqual(progresses[0]["percent"], 45)

    def test_smooth_progress_limit_uses_stage_boundary(self):
        module = load_client_module()

        limit = module.get_smooth_progress_limit({
            "stage": "analyze_log_started",
            "percent": 60,
        })

        self.assertEqual(limit, 69)

    def test_smooth_progress_limit_supports_image_stage_boundary(self):
        module = load_client_module()

        limit = module.get_smooth_progress_limit({
            "stage": "read_image_started",
            "percent": 47,
        })

        self.assertEqual(limit, 74)

    def test_next_smooth_progress_moves_forward_without_exceeding_limit(self):
        module = load_client_module()

        self.assertEqual(module.next_smooth_progress(60, 69), 61)
        self.assertEqual(module.next_smooth_progress(69, 69), 69)

    def test_progress_message_percent_follows_smooth_progress_value(self):
        module = load_client_module()

        self.assertEqual(
            module.format_progress_message_for_percent("寮€濮嬬患鍚堝垎鏋?0%", 91),
            "寮€濮嬬患鍚堝垎鏋?91%",
        )

    def test_window_starts_smooth_progress_after_backend_stage_update(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)
            window._handle_task_progress({
                "stage": "analyze_code_started",
                "stage_label": "\u7efc\u5408\u5206\u6790",
                "percent": 90,
                "message": "\u5f00\u59cb\u7efc\u5408\u5206\u6790 0%",
            })

            self.assertEqual(window.progress_animation_target, 98)
            root.update()
            self.assertIn("gpt-5.6-sol", window.progress_text.get())
            self.assertIn("深度故障推理", window.progress_text.get())
            self.assertTrue(window.progress_text.get().endswith("90%"))
        finally:
            root.destroy()

    def test_window_smoothly_animates_long_image_recognition_stage(self):
        module = load_client_module()
        root = tk.Tk()
        root.withdraw()
        try:
            window = module.LogAnalyzerWindow(root)
            window._handle_task_progress({
                "stage": "read_image_started",
                "stage_label": "\u56fe\u7247\u8bc6\u522b",
                "percent": 45,
                "message": "\u5f00\u59cb\u8bc6\u522b\u56fe\u7247 0%",
            })

            self.assertEqual(window.progress_animation_target, 74)
            root.update()
            self.assertIn("图片模型首次加载时间较长，请耐心等待", window.progress_text.get())
        finally:
            root.destroy()

    def test_deep_reasoning_progress_explains_expected_wait(self):
        module = load_client_module()
        source = inspect.getsource(module.LogAnalyzerWindow._handle_task_progress)

        self.assertIn("正在使用 gpt-5.6-sol 进行深度故障推理", source)
        self.assertIn("请耐心等待", source)

    def test_image_mode_defaults_to_log_screenshot_and_explains_types(self):
        module = load_client_module()
        init_source = inspect.getsource(module.LogAnalyzerWindow.__init__)
        layout_source = inspect.getsource(module.LogAnalyzerWindow._build_layout)

        self.assertIn('value="log_image"', init_source)
        self.assertIn("日志截图请选择 log_image", layout_source)
        self.assertIn("业务页面请选择 business_image", layout_source)

    def test_polling_stops_when_cancel_requested(self):
        module = load_client_module()

        class NeverDoneClient:
            def get_task_status(self, task_id):
                return {"task_id": task_id, "state": "PROGRESS", "ready": False}

        with self.assertRaises(module.OperationCancelled):
            module.poll_task_until_ready(
                NeverDoneClient(),
                "task-123",
                should_cancel=lambda: True,
                sleep_func=lambda seconds: None,
            )

    def test_polling_times_out_when_task_never_finishes(self):
        module = load_client_module()

        class NeverDoneClient:
            def __init__(self):
                self.calls = 0

            def get_task_status(self, task_id):
                self.calls += 1
                return {"task_id": task_id, "state": "PROGRESS", "ready": False}

        client = NeverDoneClient()

        with self.assertRaisesRegex(RuntimeError, "Celery worker"):
            module.poll_task_until_ready(
                client,
                "task-123",
                sleep_func=lambda seconds: None,
                max_polls=3,
            )

        self.assertEqual(client.calls, 3)


if __name__ == "__main__":
    unittest.main()

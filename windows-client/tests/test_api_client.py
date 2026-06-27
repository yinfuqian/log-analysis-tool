import importlib.util
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
import requests


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

    def test_builds_analysis_sections_for_popup_navigation_and_code_blocks(self):
        module = load_client_module()
        payload = {
            "task_id": "task-123",
            "repo_path": "/tmp/log-analyzer-repos/task-123/repo-master",
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
            "repo_path": "/tmp/log-analyzer-repos/task-123/repo-master",
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
            self.assertIn("http://qwbot30.wezhuiyi.com:9595/zhuiyi/logapi", joined)
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
            self.assertEqual(window.backend_url.get(), "http://qwbot30.wezhuiyi.com:9595/zhuiyi/logapi")
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
        self.assertIn("娴狅絿鐖滈幏澶婂絿 100%", statuses)
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
            self.assertEqual(window.progress_text.get(), "\u5f00\u59cb\u7efc\u5408\u5206\u6790 90%")
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
        finally:
            root.destroy()

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


if __name__ == "__main__":
    unittest.main()

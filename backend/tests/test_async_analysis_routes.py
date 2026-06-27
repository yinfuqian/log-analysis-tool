import importlib.util
import re
import sys
import tempfile
import types
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROUTES_DIR = BACKEND_DIR / "app" / "analysis" / "routes"
ROUTES_PATH = ROUTES_DIR / "routes.py"


class BlueprintStub:
    def __init__(self, *args, **kwargs):
        pass

    def route(self, *args, **kwargs):
        return lambda func: func


class FakeTaskResult:
    id = "task-123"
    state = "PENDING"


class FakeAnalyzeTask:
    def __init__(self):
        self.submitted = []

    def delay(self, data):
        self.submitted.append(data)
        return FakeTaskResult()


class FakeAsyncResult:
    info = {}

    def __init__(self, task_id, app=None):
        self.id = task_id
        self.state = "SUCCESS"
        self.result = {"code_analysis": "done"}
        self.info = self.__class__.info

    def ready(self):
        return True

    def successful(self):
        return True


def install_route_stubs():
    class FakeChatCompletions:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            message = types.SimpleNamespace(content="chat-result")
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice])

    class FakeResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return types.SimpleNamespace(output_text="responses-result")

    class FakeOpenAI:
        last_instance = None

        def __init__(self, api_key=None, base_url=None):
            self.api_key = api_key
            self.base_url = base_url
            self.chat = types.SimpleNamespace(completions=FakeChatCompletions())
            self.responses = FakeResponses()
            FakeOpenAI.last_instance = self

    flask_stub = types.ModuleType("flask")
    flask_stub.Blueprint = BlueprintStub
    flask_stub.request = types.SimpleNamespace(json={})
    flask_stub.jsonify = lambda payload: payload
    flask_stub.current_app = types.SimpleNamespace(config={}, logger=types.SimpleNamespace(
        info=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    ))
    sys.modules["flask"] = flask_stub

    celery_result_stub = types.ModuleType("celery.result")
    celery_result_stub.AsyncResult = FakeAsyncResult
    sys.modules["celery.result"] = celery_result_stub

    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = FakeOpenAI
    sys.modules["openai"] = openai_stub

    class FakeCeleryControl:
        def __init__(self):
            self.revoked = []

        def revoke(self, task_id, terminate=False, signal=None):
            self.revoked.append({
                "task_id": task_id,
                "terminate": terminate,
                "signal": signal,
            })

    fake_celery = types.SimpleNamespace(control=FakeCeleryControl())

    extensions_stub = types.ModuleType("extensions")
    extensions_stub.celery = fake_celery
    extensions_stub.db = types.SimpleNamespace(session=types.SimpleNamespace(
        add=lambda *args, **kwargs: None,
        commit=lambda *args, **kwargs: None,
        rollback=lambda *args, **kwargs: None,
    ))
    sys.modules["extensions"] = extensions_stub

    for name in ["app", "app.analysis", "app.analysis.routes", "app.logfile", "app.logfile.models"]:
        module = types.ModuleType(name)
        module.__path__ = [str(ROUTES_DIR)] if name == "app.analysis.routes" else []
        sys.modules[name] = module

    sys.modules["app"].db = types.SimpleNamespace(session=types.SimpleNamespace(
        add=lambda *args, **kwargs: None,
        commit=lambda *args, **kwargs: None,
        rollback=lambda *args, **kwargs: None,
    ))

    logfile_model_stub = types.ModuleType("app.logfile.models.model")
    logfile_model_stub.QueryRecord = lambda **kwargs: kwargs
    logfile_model_stub.AnalysisKnowledgeCase = types.SimpleNamespace
    sys.modules["app.logfile.models.model"] = logfile_model_stub

    tasks_stub = types.ModuleType("app.analysis.routes.tasks")
    tasks_stub.analyze_log_task = FakeAnalyzeTask()
    sys.modules["app.analysis.routes.tasks"] = tasks_stub
    return flask_stub, tasks_stub, fake_celery, FakeOpenAI


def load_routes_module():
    flask_stub, tasks_stub, fake_celery, fake_openai = install_route_stubs()
    spec = importlib.util.spec_from_file_location("app.analysis.routes.routes", ROUTES_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.analysis.routes.routes"] = module
    spec.loader.exec_module(module)
    return module, flask_stub, tasks_stub, fake_celery, fake_openai


class AsyncAnalysisRouteTests(unittest.TestCase):
    def test_routes_source_avoids_python310_fstring_backslash_expressions(self):
        source = ROUTES_PATH.read_text(encoding="utf-8")
        offenders = []
        f_string_prefix_pattern = re.compile(r"(^|[\s\(\[=,:])(?:[rRbBuU]*[fF][rRbBuU]*|[fF][rRbBuU]*)['\"]")
        expression_pattern = re.compile(r"\{[^{}]*\\[^{}]*\}")

        for line_number, line in enumerate(source.splitlines(), start=1):
            if "\\" not in line or not f_string_prefix_pattern.search(line):
                continue
            if expression_pattern.search(line):
                offenders.append(f"{line_number}: {line.strip()}")

        self.assertEqual(
            offenders,
            [],
            "Python 3.10 cannot parse backslashes inside f-string expressions.",
        )

    def test_submit_async_returns_task_id(self):
        routes, flask_stub, tasks_stub, _, _ = load_routes_module()
        flask_stub.request.json = {
            "productId": "1",
            "moduleId": "2",
            "branchAddress": "https://git.example/repo.git",
            "tagVersion": "v1",
            "file_path": "/data/upload/log.txt",
        }

        payload, status = routes.submit_async_analysis()

        self.assertEqual(status, 202)
        self.assertEqual(payload["task_id"], "task-123")
        self.assertEqual(tasks_stub.analyze_log_task.submitted[0]["productId"], "1")

    def test_submit_async_validates_required_fields(self):
        routes, flask_stub, _, _, _ = load_routes_module()
        flask_stub.request.json = {"productId": "1"}

        payload, status = routes.submit_async_analysis()

        self.assertEqual(status, 400)
        self.assertIn("moduleId", payload["missing_fields"])

    def test_submit_async_requires_image_tag_for_image_source(self):
        routes, flask_stub, _, _, _ = load_routes_module()
        flask_stub.request.json = {
            "productId": "1",
            "moduleId": "2",
            "branchAddress": "https://git.example/repo.git",
            "tagVersion": "v1",
            "file_path": "/data/upload/demo-image.png",
            "source_type": "image",
        }

        payload, status = routes.submit_async_analysis()

        self.assertEqual(status, 400)
        self.assertIn("image_tag", payload["missing_fields"])

    def test_get_task_status_returns_success_result(self):
        routes, _, _, _, _ = load_routes_module()

        payload = routes.get_analysis_task("task-123")

        self.assertTrue(payload["ready"])
        self.assertTrue(payload["successful"])
        self.assertEqual(payload["result"]["code_analysis"], "done")

    def test_get_task_status_returns_progress_meta(self):
        original_info = FakeAsyncResult.info
        FakeAsyncResult.info = {
            "stage": "clone_repo_done",
            "stage_label": "浠ｇ爜鎷夊彇",
            "stage_percent": 100,
            "percent": 45,
            "message": "浠ｇ爜鎷夊彇 100%",
        }
        try:
            routes, _, _, _, _ = load_routes_module()

            payload = routes.get_analysis_task("task-123")
        finally:
            FakeAsyncResult.info = original_info

        self.assertEqual(payload["progress"]["stage"], "clone_repo_done")
        self.assertEqual(payload["progress"]["message"], "浠ｇ爜鎷夊彇 100%")
        self.assertEqual(payload["progress"]["percent"], 45)

    def test_cancel_task_revokes_celery_task(self):
        routes, _, _, fake_celery, _ = load_routes_module()

        payload, status = routes.cancel_analysis_task("task-123")

        self.assertEqual(status, 202)
        self.assertEqual(payload["state"], "REVOKED")
        self.assertEqual(fake_celery.control.revoked[0]["task_id"], "task-123")
        self.assertTrue(fake_celery.control.revoked[0]["terminate"])
        self.assertEqual(fake_celery.control.revoked[0]["signal"], "SIGTERM")

    def test_insert_query_record_accepts_business_status_keyword(self):
        routes, flask_stub, _, _, _ = load_routes_module()
        created_records = []

        def fake_query_record(**kwargs):
            created_records.append(kwargs)
            return kwargs

        routes.QueryRecord = fake_query_record
        routes.db = types.SimpleNamespace(session=types.SimpleNamespace(
            add=lambda *args, **kwargs: None,
            commit=lambda *args, **kwargs: None,
            rollback=lambda *args, **kwargs: None,
        ))
        flask_stub.current_app.config = {"OPENAI_MODEL": "gpt-5.5"}

        routes.insert_query_record(
            {
                "productId": "45",
                "moduleId": "251",
                "log_id": 25,
                "file_path": "/data/upload/demo.log",
                "branchAddress": "https://code.in.wezhuiyi.com/pal/demo.git",
                "tagVersion": "v1.0.0",
            },
            0,
            status="cache_hit",
            hit_cache=True,
            knowledge_case_id=7,
        )

        self.assertEqual(created_records[0]["answer"], 0)
        self.assertEqual(created_records[0]["status"], "cache_hit")
        self.assertTrue(created_records[0]["hit_cache"])
        self.assertEqual(created_records[0]["knowledge_case_id"], 7)

    def test_ai_model_uses_chat_completions_by_default(self):
        routes, flask_stub, _, _, fake_openai = load_routes_module()
        flask_stub.current_app.config = {
            "OPENAI_KEY": "token",
            "OPENAI_URL": "https://newapi.in.wezhuiyi.com/v1",
            "OPENAI_MODEL": "gpt-5-codex",
        }

        result = routes.call_ai_model("system prompt", "user prompt")

        self.assertEqual(result, "chat-result")
        self.assertEqual(fake_openai.last_instance.base_url, "https://newapi.in.wezhuiyi.com/v1")
        call = fake_openai.last_instance.chat.completions.calls[0]
        self.assertEqual(call["model"], "gpt-5-codex")
        self.assertEqual(call["messages"][0]["role"], "system")

    def test_ai_model_can_use_responses_api_style(self):
        routes, flask_stub, _, _, fake_openai = load_routes_module()
        flask_stub.current_app.config = {
            "OPENAI_KEY": "token",
            "OPENAI_URL": "https://newapi.in.wezhuiyi.com/v1",
            "OPENAI_MODEL": "gpt-5-codex",
            "OPENAI_API_STYLE": "responses",
        }

        result = routes.call_ai_model("system prompt", "user prompt")

        self.assertEqual(result, "responses-result")
        call = fake_openai.last_instance.responses.calls[0]
        self.assertEqual(call["model"], "gpt-5-codex")
        self.assertEqual(call["input"][0]["role"], "system")

    def test_multimodal_ai_model_uses_image_input_blocks(self):
        routes, flask_stub, _, _, fake_openai = load_routes_module()
        flask_stub.current_app.config = {
            "OPENAI_KEY": "token",
            "OPENAI_URL": "https://newapi.in.wezhuiyi.com/v1",
            "OPENAI_MODEL": "gpt-5.5",
            "OPENAI_API_STYLE": "responses",
        }

        result = routes.call_ai_multimodal_model(
            "system prompt",
            "user prompt",
            "data:image/png;base64,ZmFrZQ==",
        )

        self.assertEqual(result, "responses-result")
        call = fake_openai.last_instance.responses.calls[0]
        self.assertEqual(call["model"], "gpt-5.5")
        self.assertEqual(call["input"][1]["content"][1]["type"], "input_image")

    def test_multimodal_ai_model_accepts_multiple_image_inputs(self):
        routes, flask_stub, _, _, fake_openai = load_routes_module()
        flask_stub.current_app.config = {
            "OPENAI_KEY": "token",
            "OPENAI_URL": "https://newapi.in.wezhuiyi.com/v1",
            "OPENAI_MODEL": "gpt-5.5",
            "OPENAI_API_STYLE": "responses",
        }

        result = routes.call_ai_multimodal_model(
            "system prompt",
            "user prompt",
            [
                "data:image/png;base64,ZmFrZTE=",
                "data:image/png;base64,ZmFrZTI=",
            ],
        )

        self.assertEqual(result, "responses-result")
        content = fake_openai.last_instance.responses.calls[0]["input"][1]["content"]
        self.assertEqual([item["type"] for item in content], ["input_text", "input_image", "input_image"])

    def test_build_image_analysis_context_includes_description_keywords_and_text(self):
        routes, _, _, _, _ = load_routes_module()

        context = routes.build_image_analysis_context(
            {
                "image_tag": "business_image",
                "summary": "订单详情页提示 Redis 连接异常",
                "extracted_text": "Redis connection reset by peer",
                "keywords": ["redis", "order", "timeout"],
                "components": ["redis"],
            },
            "点击保存订单时报错",
        )

        self.assertIn("业务截图", context)
        self.assertIn("点击保存订单时报错", context)
        self.assertIn("Redis connection reset by peer", context)
        self.assertIn("redis", context.lower())

    def test_code_analysis_prompt_includes_raw_log_summary_and_code(self):
        routes, flask_stub, _, _, fake_openai = load_routes_module()
        flask_stub.current_app.config = {
            "OPENAI_KEY": "token",
            "OPENAI_URL": "https://newapi.in.wezhuiyi.com/v1",
            "OPENAI_MODEL": "gpt-5.5",
        }
        code_snippets = [{
            "file": "src/main/java/Demo.java",
            "line": 42,
            "snippet": "client.newCall(request).execute();",
        }]

        result = routes.analyze_code_with_deepseek(
            "A connection was leaked.",
            "Initial analysis says OkHttp ResponseBody was not closed.",
            code_snippets,
        )

        self.assertEqual(result, "chat-result")
        prompt = fake_openai.last_instance.chat.completions.calls[0]["messages"][1]["content"]
        self.assertIn("A connection was leaked.", prompt)
        self.assertIn("Initial analysis says OkHttp ResponseBody was not closed.", prompt)
        self.assertIn("client.newCall(request).execute();", prompt)
        self.assertIn("src/main/java/Demo.java", prompt)
        self.assertIn("src/main/java/Demo.java", prompt)
        self.assertIn("client.newCall(request).execute()", prompt)
        self.assertIn("完整日志上下文", prompt)
        self.assertIn("possible_causes", prompt)
        self.assertIn("config_issue", prompt)
        self.assertIn("network_issue", prompt)
        self.assertIn("code_issue", prompt)
        self.assertIn("query_commands", prompt)
        self.assertIn("fix_commands", prompt)

    def test_log_analysis_prompt_requires_full_context_not_only_error_lines(self):
        routes, flask_stub, _, _, fake_openai = load_routes_module()
        flask_stub.current_app.config = {
            "OPENAI_KEY": "token",
            "OPENAI_URL": "https://newapi.in.wezhuiyi.com/v1",
            "OPENAI_MODEL": "gpt-5.5",
        }
        log_content = "\n".join([
            "2026-06-07 12:30:44 INFO request started",
            "2026-06-07 12:30:45 WARN redis latency is high",
            "2026-06-07 12:30:46 ERROR failed",
            "2026-06-07 12:30:47 INFO request finished",
        ])

        result = routes.analyze_log_with_deepseek(log_content)

        self.assertEqual(result, "chat-result")
        prompt = fake_openai.last_instance.chat.completions.calls[0]["messages"][1]["content"]
        self.assertIn("完整日志上下文", prompt)
        self.assertIn("不要只根据 ERROR", prompt)
        self.assertIn("INFO request started", prompt)
        self.assertIn("WARN redis latency is high", prompt)
        self.assertIn("配置", prompt)
        self.assertIn("网络", prompt)

    def test_large_log_analysis_uses_error_context_instead_of_chunking_full_log(self):
        routes, _, _, _, _ = load_routes_module()
        original_call_ai_model = routes.call_ai_model
        calls = []

        def fake_call_ai_model(system_prompt, user_prompt):
            calls.append(user_prompt)
            return f"summary-{len(calls)}"

        routes.call_ai_model = fake_call_ai_model
        try:
            log_content = "\n".join(
                [f"2026-06-07 12:29:{index:02d} INFO noise {index}" for index in range(20)]
                + [
                    "2026-06-07 12:30:44 INFO request started",
                    "2026-06-07 12:30:45 WARN redis latency is high",
                    "2026-06-07 12:30:46 ERROR failed",
                    "    at demo.Target.run(Target.java:42)",
                    "2026-06-07 12:30:47 INFO request finished",
                ]
                + [f"2026-06-07 12:31:{index:02d} INFO tail noise {index}" for index in range(20)]
            )

            result = routes.analyze_log_with_deepseek(log_content)
        finally:
            routes.call_ai_model = original_call_ai_model

        self.assertEqual(result, "summary-1")
        self.assertEqual(len(calls), 1)
        self.assertIn("\u65e5\u5fd7\u9519\u8bef\u5173\u952e\u6bb5\u53ca\u4e0a\u4e0b\u6587", calls[0])
        self.assertIn("INFO request started", calls[0])
        self.assertIn("WARN redis latency is high", calls[0])
        self.assertIn("ERROR failed", calls[0])
        self.assertIn("Target.java:42", calls[0])
        self.assertNotIn("INFO noise 0", calls[0])
        self.assertNotIn("tail noise 19", calls[0])

    def test_code_analysis_compacts_oversized_log_context(self):
        routes, flask_stub, _, _, fake_openai = load_routes_module()
        flask_stub.current_app.config = {
            "OPENAI_KEY": "token",
            "OPENAI_URL": "https://newapi.in.wezhuiyi.com/v1",
            "OPENAI_MODEL": "gpt-5.5",
            "LOG_CONTEXT_MAX_CHARS": 2000,
        }
        large_log = "\n".join([
            "2026-06-07 12:30:44 INFO request started",
            "2026-06-07 12:30:45 WARN redis latency is high",
            "2026-06-07 12:30:46 ERROR failed with important stack",
            "2026-06-07 12:30:47 INFO request finished",
        ])

        result = routes.analyze_code_with_deepseek(
            large_log,
            "error context summary",
            [{"file": "Demo.java", "line": 42, "snippet": "throw ex;"}],
        )

        self.assertEqual(result, "chat-result")
        prompt = fake_openai.last_instance.chat.completions.calls[0]["messages"][1]["content"]
        self.assertIn("\u65e5\u5fd7\u9519\u8bef\u5173\u952e\u6bb5\u53ca\u4e0a\u4e0b\u6587", prompt)
        self.assertIn("ERROR failed with important stack", prompt)
        self.assertNotIn(large_log, prompt)

    def test_extracts_python_traceback_file_and_line(self):
        routes, _, _, _, _ = load_routes_module()
        log_content = '''Traceback (most recent call last):
  File "app.py", line 42, in <module>
    result = process_data(data)
  File "utils.py", line 18, in process_data
    return data / 0
ZeroDivisionError: division by zero
'''

        result = routes.extract_error_info_from_log(log_content)

        self.assertEqual(result[0]["file"], "app.py")
        self.assertEqual(result[0]["line"], 42)
        self.assertEqual(result[0]["error"], "ZeroDivisionError: division by zero")
        self.assertEqual(result[1]["file"], "utils.py")
        self.assertEqual(result[1]["line"], 18)

    def test_resolves_python_traceback_and_extracts_code_snippet(self):
        routes, _, _, _, _ = load_routes_module()
        with tempfile.TemporaryDirectory() as repo_dir:
            app_file = Path(repo_dir) / "app.py"
            app_file.write_text(
                "\n".join(f"line {index}" for index in range(1, 51)),
                encoding="utf-8",
            )

            resolved = routes.resolve_file_paths(
                repo_dir,
                [{"file": "app.py", "line": 42, "error": "ZeroDivisionError: division by zero"}],
            )
            snippets = routes.extract_code_snippets(resolved)

        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0]["line"], 42)
        self.assertIn("app.py", snippets[0]["file"])
        self.assertIn("line 42", snippets[0]["snippet"])
        self.assertEqual(snippets[0]["start_line"], 37)
        self.assertEqual(snippets[0]["end_line"], 46)
        self.assertIn(">>   42 | line 42", snippets[0]["numbered_snippet"])

    def test_build_code_findings_names_file_line_and_code_block(self):
        routes, _, _, _, _ = load_routes_module()
        findings = routes.build_code_findings([
            {
                "file": "src/main/java/demo/QualitySessionDataRemoveHandler.java",
                "line": 28,
                "start_line": 24,
                "end_line": 33,
                "numbered_snippet": "     27 | before();\n>>   28 | removeSession();",
                "snippet": "before();\nremoveSession();",
            }
        ])

        self.assertEqual(findings[0]["file"], "src/main/java/demo/QualitySessionDataRemoveHandler.java")
        self.assertEqual(findings[0]["line"], 28)
        self.assertIn("28", findings[0]["reason"])
        self.assertIn(">>   28 | removeSession();", findings[0]["code"])

    def test_finds_component_code_usages_for_redis_and_flyway_errors(self):
        routes, _, _, _, _ = load_routes_module()
        with tempfile.TemporaryDirectory() as repo_dir:
            redis_file = Path(repo_dir) / "RedisCacheService.java"
            redis_file.write_text(
                "\n".join([
                    "class RedisCacheService {",
                    "  private RedisTemplate redisTemplate;",
                    "  void save(String key) { redisTemplate.opsForValue().set(key, \"1\"); }",
                    "}",
                ]),
                encoding="utf-8",
            )
            flyway_file = Path(repo_dir) / "FlywayConfig.java"
            flyway_file.write_text(
                "\n".join([
                    "class FlywayConfig {",
                    "  Flyway flyway() {",
                    "    return Flyway.configure().baselineOnMigrate(true).load();",
                    "  }",
                    "}",
                ]),
                encoding="utf-8",
            )

            redis_components = routes.detect_error_components("Redis connection reset by peer")
            flyway_components = routes.detect_error_components("Flyway migration failed")
            redis_snippets = routes.find_component_code_usages(repo_dir, redis_components)
            flyway_snippets = routes.find_component_code_usages(repo_dir, flyway_components)

        self.assertIn("redis", redis_components)
        self.assertTrue(any("RedisCacheService.java" in item["file"] for item in redis_snippets))
        self.assertTrue(any("RedisTemplate" in item["numbered_snippet"] for item in redis_snippets))
        self.assertIn("flyway", flyway_components)
        self.assertTrue(any("FlywayConfig.java" in item["file"] for item in flyway_snippets))
        self.assertTrue(any("Flyway.configure" in item["numbered_snippet"] for item in flyway_snippets))

    def test_error_fingerprint_ignores_dynamic_ids_and_timestamps(self):
        routes, _, _, _, _ = load_routes_module()
        error_info = [{
            "file": "RedisClient.java",
            "line": 88,
            "error": "ConnectionResetError: userId=12345 requestId=abc-123 at 2026-06-13 15:30:01",
        }]

        first = routes.build_error_fingerprint("45", "251", error_info)
        error_info[0]["error"] = "ConnectionResetError: userId=67890 requestId=xyz-999 at 2026-06-14 16:31:02"
        second = routes.build_error_fingerprint("45", "251", error_info)

        self.assertEqual(first, second)

    def test_error_fingerprint_is_scoped_by_branch_version(self):
        routes, _, _, _, _ = load_routes_module()
        error_info = [{
            "file": "Demo.java",
            "line": 42,
            "error": "java.lang.NullPointerException: null",
        }]

        release_fingerprint = routes.build_error_fingerprint(
            "45",
            "251",
            error_info,
            "https://code.in.wezhuiyi.com/pal/pal-quality-inspection.git",
            "release_zyzx/1.3.2",
        )
        old_tag_fingerprint = routes.build_error_fingerprint(
            "45",
            "251",
            error_info,
            "https://code.in.wezhuiyi.com/pal/pal-quality-inspection.git",
            "v0.23.29-ZYKJ20220503001-rc1",
        )

        self.assertNotEqual(release_fingerprint, old_tag_fingerprint)

    def test_parses_structured_issue_conclusion_from_ai_json(self):
        routes, _, _, _, _ = load_routes_module()
        ai_text = """
        ```json
        {
          "issue_category": "network_issue",
          "conclusion_summary": "Redis connection was reset.",
          "root_cause": "The broker closed the socket.",
          "solution": "Check Redis timeout and keepalive.",
          "query_commands": ["redis-cli -h 127.0.0.1 -p 6379 ping"],
          "fix_commands": ["redis-cli CONFIG SET timeout 300"],
          "confidence": 0.82,
          "possible_causes": {
            "code_issue": {"possible": false, "confidence": 0.2, "reason": "No code evidence"},
            "config_issue": {"possible": true, "confidence": 0.6, "reason": "Timeout may be too short"},
            "network_issue": {"possible": true, "confidence": 0.9, "reason": "Connection reset by peer"}
          },
          "evidence": ["Connection reset by peer"]
        }
        ```
        """

        conclusion = routes.parse_issue_conclusion(ai_text)

        self.assertEqual(conclusion["issue_category"], "network_issue")
        self.assertEqual(conclusion["issue_category_label"], "网络问题")
        self.assertEqual(conclusion["confidence"], 0.82)
        self.assertIn("Connection reset by peer", conclusion["evidence"])
        self.assertFalse(conclusion["possible_causes"]["code_issue"]["possible"])
        self.assertTrue(conclusion["possible_causes"]["config_issue"]["possible"])
        self.assertTrue(conclusion["possible_causes"]["network_issue"]["possible"])
        self.assertEqual(conclusion["possible_causes"]["network_issue"]["confidence"], 0.9)
        self.assertEqual(conclusion["query_commands"][0], "redis-cli -h 127.0.0.1 -p 6379 ping")
        self.assertEqual(conclusion["fix_commands"][0], "redis-cli CONFIG SET timeout 300")

    def test_parse_issue_conclusion_normalizes_command_lists(self):
        routes, _, _, _, _ = load_routes_module()

        conclusion = routes.parse_issue_conclusion(
            """
            {
              "issue_category": "config_issue",
              "query_commands": "grep -n 'timeout' application.yml",
              "fix_commands": ["sed -i 's/timeout: 30/timeout: 300/' application.yml", ""]
            }
            """
        )

        self.assertEqual(conclusion["query_commands"], ["grep -n 'timeout' application.yml"])
        self.assertEqual(conclusion["fix_commands"], ["sed -i 's/timeout: 30/timeout: 300/' application.yml"])

    def test_issue_category_labels_are_readable_chinese(self):
        routes, _, _, _, _ = load_routes_module()

        self.assertEqual(routes.ISSUE_CATEGORY_LABELS["code_issue"], "代码问题")
        self.assertEqual(routes.ISSUE_CATEGORY_LABELS["data_issue"], "数据问题")
        self.assertEqual(routes.ISSUE_CATEGORY_LABELS["config_issue"], "配置问题")
        self.assertEqual(routes.ISSUE_CATEGORY_LABELS["network_issue"], "网络问题")
        self.assertEqual(routes.ISSUE_CATEGORY_LABELS["resource_issue"], "资源问题")
        self.assertEqual(routes.ISSUE_CATEGORY_LABELS["unknown"], "未知")

    def test_parse_issue_conclusion_falls_back_to_unknown(self):
        routes, _, _, _, _ = load_routes_module()

        conclusion = routes.parse_issue_conclusion("plain text result")

        self.assertEqual(conclusion["issue_category"], "unknown")
        self.assertEqual(conclusion["confidence"], 0)
        self.assertEqual(conclusion["raw_analysis"], "plain text result")


if __name__ == "__main__":
    unittest.main()

import importlib.util
import os
import tempfile
import sys
import types
import unittest
from pathlib import Path


TASKS_PATH = Path(__file__).resolve().parents[1] / "app" / "analysis" / "routes" / "tasks.py"


class FakeCelery:
    def task(self, *args, **kwargs):
        return lambda func: func


class FakeTask:
    def __init__(self):
        self.states = []

    def update_state(self, state=None, meta=None):
        self.states.append({"state": state, "meta": meta})


def load_tasks_module():
    extensions_stub = types.ModuleType("extensions")
    extensions_stub.celery = FakeCelery()
    sys.modules["extensions"] = extensions_stub

    spec = importlib.util.spec_from_file_location("analysis_tasks_under_test", TASKS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AnalysisTaskProgressTests(unittest.TestCase):
    def test_report_progress_updates_celery_meta_with_stage_message(self):
        module = load_tasks_module()
        task = FakeTask()

        module.report_progress(
            task,
            stage="clone_repo_done",
            stage_label="代码拉取",
            stage_percent=100,
            percent=45,
        )

        self.assertEqual(task.states[0]["state"], "PROGRESS")
        self.assertEqual(task.states[0]["meta"]["stage"], "clone_repo_done")
        self.assertEqual(task.states[0]["meta"]["stage_label"], "代码拉取")
        self.assertEqual(task.states[0]["meta"]["stage_percent"], 100)
        self.assertEqual(task.states[0]["meta"]["percent"], 45)
        self.assertEqual(task.states[0]["meta"]["message"], "代码拉取 100%")

    def test_build_analysis_evidence_marks_when_code_context_was_used(self):
        module = load_tasks_module()
        error_info = [{"file": "Demo.java", "line": 12, "error": "boom"}]
        resolved_errors = [{"file": "/repo/Demo.java", "line": 12, "error": "boom"}]
        code_snippets = [{"file": "/repo/Demo.java", "line": 12, "snippet": "throw boom;"}]

        evidence = module.build_analysis_evidence(error_info, resolved_errors, code_snippets)

        self.assertTrue(evidence["used_code_context"])
        self.assertEqual(evidence["error_info_count"], 1)
        self.assertEqual(evidence["resolved_file_count"], 1)
        self.assertEqual(evidence["code_snippet_count"], 1)
        self.assertEqual(evidence["code_snippet_files"], ["/repo/Demo.java"])

    def test_build_analysis_evidence_marks_when_code_context_is_missing(self):
        module = load_tasks_module()

        evidence = module.build_analysis_evidence(
            error_info=[{"file": "Missing.java", "line": 12, "error": "boom"}],
            resolved_errors=[],
            code_snippets=[],
        )

        self.assertFalse(evidence["used_code_context"])
        self.assertEqual(evidence["resolved_file_count"], 0)
        self.assertEqual(evidence["code_snippet_count"], 0)

    def test_cleanup_analysis_files_removes_only_task_upload_and_repo_workspace(self):
        module = load_tasks_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = os.path.join(temp_dir, "upload")
            repo_base_dir = os.path.join(temp_dir, "repos")
            task_id = "task-123"
            os.makedirs(upload_dir)
            os.makedirs(os.path.join(repo_base_dir, task_id, "demo-repo"))

            uploaded_file = os.path.join(upload_dir, "demo.log")
            repo_file = os.path.join(repo_base_dir, task_id, "demo-repo", "Demo.java")
            outside_file = os.path.join(temp_dir, "outside.log")
            Path(uploaded_file).write_text("log", encoding="utf-8")
            Path(repo_file).write_text("class Demo {}", encoding="utf-8")
            Path(outside_file).write_text("keep", encoding="utf-8")

            result = module.cleanup_analysis_files(
                {"file_path": uploaded_file},
                repo_path=os.path.join(repo_base_dir, task_id, "demo-repo"),
                task_id=task_id,
                upload_dir=upload_dir,
                repo_base_dir=repo_base_dir,
            )

            self.assertTrue(result["uploaded_file_removed"])
            self.assertTrue(result["repo_workspace_removed"])
            self.assertFalse(os.path.exists(uploaded_file))
            self.assertFalse(os.path.exists(os.path.join(repo_base_dir, task_id)))
            self.assertTrue(os.path.exists(outside_file))

    def test_cleanup_analysis_files_refuses_paths_outside_allowed_roots(self):
        module = load_tasks_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = os.path.join(temp_dir, "upload")
            repo_base_dir = os.path.join(temp_dir, "repos")
            os.makedirs(upload_dir)
            os.makedirs(repo_base_dir)

            outside_file = os.path.join(temp_dir, "outside.log")
            outside_repo = os.path.join(temp_dir, "outside-repo")
            Path(outside_file).write_text("keep", encoding="utf-8")
            os.makedirs(outside_repo)

            result = module.cleanup_analysis_files(
                {"file_path": outside_file},
                repo_path=outside_repo,
                task_id="task-123",
                upload_dir=upload_dir,
                repo_base_dir=repo_base_dir,
            )

            self.assertFalse(result["uploaded_file_removed"])
            self.assertFalse(result["repo_workspace_removed"])
            self.assertTrue(os.path.exists(outside_file))
            self.assertTrue(os.path.exists(outside_repo))


if __name__ == "__main__":
    unittest.main()

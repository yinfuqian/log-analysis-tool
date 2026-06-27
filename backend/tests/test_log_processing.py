import gzip
import io
import importlib.util
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]
LOG_PROCESSING_PATH = BACKEND_DIR / "app" / "logfile" / "routes" / "log_processing.py"
UTILS_PATH = BACKEND_DIR / "app" / "logfile" / "routes" / "utils.py"


def load_module(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


log_processing = load_module("log_processing_under_test", LOG_PROCESSING_PATH)
extract_log_date = log_processing.extract_log_date
filter_lines_by_date = log_processing.filter_lines_by_date
read_uploaded_log_lines = log_processing.read_uploaded_log_lines
resolve_target_date = log_processing.resolve_target_date


def load_utils_module():
    flask_stub = types.ModuleType("flask")
    flask_stub.current_app = types.SimpleNamespace(logger=types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    ))
    sys.modules.setdefault("flask", flask_stub)
    sys.modules.setdefault("app", types.ModuleType("app"))
    sys.modules.setdefault("app.utils", types.ModuleType("app.utils"))
    save_log_file_stub = types.ModuleType("app.utils.save_log_file")
    save_log_file_stub.save_log_file = lambda *args, **kwargs: None
    sys.modules.setdefault("app.utils.save_log_file", save_log_file_stub)
    for name in [
        "app.product",
        "app.product.models",
        "app.product.models.model",
        "app.modules",
        "app.modules.models",
        "app.modules.models.model",
        "app.branches",
        "app.branches.models",
        "app.branches.models.model",
    ]:
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules["app.product.models.model"].Product = object
    sys.modules["app.modules.models.model"].Module = object
    sys.modules["app.branches.models.model"].Branch = object
    return load_module("logfile_utils_under_test", UTILS_PATH)


class UploadedFileStub:
    def __init__(self, data):
        self.stream = io.BytesIO(data)


class LogProcessingTests(unittest.TestCase):
    def test_reads_gzip_file_as_text_lines(self):
        payload = "2026-06-07 12:30:45 ERROR boom\nCaused by: bad config\n"
        compressed = gzip.compress(payload.encode("utf-8"))

        lines = read_uploaded_log_lines(UploadedFileStub(compressed), "app.log.gz")

        self.assertEqual(lines, [
            "2026-06-07 12:30:45 ERROR boom",
            "Caused by: bad config",
        ])

    def test_reads_plain_log_and_txt_files_as_text_lines(self):
        payload = "2026-06-07 12:30:45 ERROR boom\nCaused by: bad config\n"

        for filename in ["app.log", "app.txt"]:
            with self.subTest(filename=filename):
                lines = read_uploaded_log_lines(UploadedFileStub(payload.encode("utf-8")), filename)

                self.assertEqual(lines, [
                    "2026-06-07 12:30:45 ERROR boom",
                    "Caused by: bad config",
                ])

    def test_resolves_relative_day_offset_against_server_date(self):
        self.assertEqual(resolve_target_date("-3", today=date(2026, 6, 10)), date(2026, 6, 7))

    def test_extracts_dates_from_common_log_timestamp_formats(self):
        samples = [
            "2026-06-07 12:30:45.123 ERROR boom",
            "2026-06-07 12:30:45 ERROR boom",
            "2026-06-07 12:30:45,123 ERROR boom",
            "2026-06-07T12:30:45.123Z ERROR boom",
            "2026/06/07 12:30:45 ERROR boom",
            "[2026-06-07 12:30:45] ERROR boom",
            "2026-06-07 ERROR boom",
        ]

        extracted = [extract_log_date(line) for line in samples]

        self.assertEqual(extracted, [date(2026, 6, 7)] * len(samples))

    def test_filters_target_date_and_preserves_java_stack_trace_context(self):
        lines = [
            "2026-06-06 23:59:59 ERROR old failure",
            "    at demo.Old.run(Old.java:1)",
            "2026-06-07 12:30:45 ERROR target failure",
            "    at demo.Target.run(Target.java:42)",
            "Caused by: java.lang.IllegalStateException: bad state",
            "... 12 common frames omitted",
            "2026-06-08 00:00:01 ERROR next failure",
            "    at demo.Next.run(Next.java:8)",
        ]

        result = filter_lines_by_date(lines, date(2026, 6, 7))

        self.assertTrue(result.date_filter_applied)
        self.assertEqual(result.filtered_lines, [
            "2026-06-07 12:30:45 ERROR target failure",
            "    at demo.Target.run(Target.java:42)",
            "Caused by: java.lang.IllegalStateException: bad state",
            "... 12 common frames omitted",
        ])
        self.assertEqual(result.original_line_count, 8)
        self.assertEqual(result.filtered_line_count, 4)
        self.assertEqual(result.matched_line_count, 1)

    def test_keeps_content_when_no_timestamps_are_recognized(self):
        lines = [
            "ERROR no timestamp here",
            "    at demo.Service.run(Service.java:10)",
        ]

        result = filter_lines_by_date(lines, date(2026, 6, 7))

        self.assertFalse(result.date_filter_applied)
        self.assertEqual(result.filtered_lines, lines)
        self.assertIn("没有识别到", result.warning)

    def test_extract_error_logs_accepts_text_lines(self):
        lines = [
            "2026-06-07 12:30:45 INFO healthy",
            "2026-06-07 12:30:46 ERROR failed",
        ]
        utils = load_utils_module()

        self.assertEqual(utils.extract_error_logs(lines), ["2026-06-07 12:30:46 ERROR failed"])

    def test_branch_lookup_accepts_live_git_branch_version_for_known_repo_url(self):
        utils = load_utils_module()
        utils.app = SimpleNamespace(logger=SimpleNamespace(
            debug=lambda *args, **kwargs: None,
            error=lambda *args, **kwargs: None,
        ))
        repo_url = "https://code.example/group/repo.git"

        class FakeBranchQuery:
            def __init__(self):
                self.filters = []

            def filter_by(self, **kwargs):
                self.filters.append(kwargs)
                return self

            def first(self):
                if self.filters[-1] == {"address": repo_url, "tag_version": "feature/demo"}:
                    return None
                if self.filters[-1] == {"address": repo_url}:
                    return SimpleNamespace(address=repo_url)
                return None

        utils.Branch = SimpleNamespace(query=FakeBranchQuery())

        address, tag_version = utils.get_branch_address_by_name(repo_url, "feature/demo")

        self.assertEqual(address, repo_url)
        self.assertEqual(tag_version, "feature/demo")


if __name__ == "__main__":
    unittest.main()

import gzip
import importlib.util
import io
import sys
import tempfile
import types
import unittest
from pathlib import Path

from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROUTES_DIR = BACKEND_DIR / "app" / "logfile" / "routes"
ROUTES_PATH = ROUTES_DIR / "routes.py"


class UploadedFileStub:
    def __init__(self, data):
        self.stream = io.BytesIO(data)


class ImageFileStub:
    def __init__(self, filename, data):
        self.filename = filename
        self.stream = io.BytesIO(data)

    def read(self, size=-1):
        return self.stream.read(size)


def make_image_bytes(image_format):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color="white").save(buffer, format=image_format)
    return buffer.getvalue()


def install_route_stubs():
    flask_stub = types.ModuleType("flask")

    class BlueprintStub:
        def __init__(self, *args, **kwargs):
            pass

        def route(self, *args, **kwargs):
            return lambda func: func

    flask_stub.Blueprint = BlueprintStub
    flask_stub.request = types.SimpleNamespace(files={}, form={})
    flask_stub.jsonify = lambda payload: payload
    flask_stub.current_app = types.SimpleNamespace(logger=types.SimpleNamespace(
        debug=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    ))
    sys.modules["flask"] = flask_stub

    for name in ["app", "app.logfile", "app.logfile.routes"]:
        module = types.ModuleType(name)
        if name == "app":
            module.__path__ = [str(BACKEND_DIR / "app")]
        elif name == "app.logfile":
            module.__path__ = [str(BACKEND_DIR / "app" / "logfile")]
        else:
            module.__path__ = [str(ROUTES_DIR)]
        sys.modules[name] = module

    models_stub = types.ModuleType("app.logfile.models")
    models_stub.Log = object
    sys.modules["app.logfile.models"] = models_stub

    extensions_stub = types.ModuleType("extensions")
    extensions_stub.db = object()
    sys.modules["extensions"] = extensions_stub

    utils_stub = types.ModuleType("app.logfile.routes.utils")
    utils_stub.extract_error_logs = lambda lines: [line for line in lines if "INFO" not in line]
    utils_stub.process_log_file = lambda lines: lines
    utils_stub.remove_duplicates = lambda lines: list(dict.fromkeys(lines))
    utils_stub.sanitize_filename = lambda filename: filename.replace("/", "_")
    utils_stub.get_product_name_by_id = lambda product_id: "product"
    utils_stub.get_module_name_by_id = lambda module_id: "module"
    utils_stub.get_branch_address_by_name = lambda address, tag_version: (address, tag_version)
    utils_stub.save_processed_log_file = lambda lines, filename: f"/tmp/{filename}"
    utils_stub.save_binary_upload_file = lambda file_bytes, filename: f"/tmp/{filename}"
    sys.modules["app.logfile.routes.utils"] = utils_stub


def load_routes_module():
    install_route_stubs()
    spec = importlib.util.spec_from_file_location("app.logfile.routes.routes", ROUTES_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.logfile.routes.routes"] = module
    spec.loader.exec_module(module)
    return module


class UploadProcessingFlowTests(unittest.TestCase):
    def test_upload_log_names_include_unique_suffix_to_avoid_concurrent_overwrite(self):
        routes = load_routes_module()

        first_name = routes.build_upload_log_name(
            "product",
            "module",
            "https://code.example/group/repo.git",
            "master",
            "server.log",
        )
        second_name = routes.build_upload_log_name(
            "product",
            "module",
            "https://code.example/group/repo.git",
            "master",
            "server.log",
        )

        self.assertNotEqual(first_name, second_name)
        self.assertTrue(first_name.endswith(".log"))
        self.assertIn("product-module-", first_name)

    def test_prepares_gzip_upload_with_date_filter_metadata(self):
        routes = load_routes_module()
        payload = "\n".join([
            "2026-06-06 23:59:59 ERROR old",
            "    at demo.Old.run(Old.java:1)",
            "2026-06-07 12:30:45 ERROR target",
            "2026-06-07 12:30:46 INFO target context",
            "    at demo.Target.run(Target.java:42)",
            "2026-06-08 00:00:01 INFO next",
        ])
        uploaded_file = UploadedFileStub(gzip.compress(payload.encode("utf-8")))

        result = routes.prepare_uploaded_log(
            uploaded_file=uploaded_file,
            original_filename="server.log.gz",
            log_name="product-module-branch-v1-20260610.gz",
            date_filter="2026-06-07",
        )

        self.assertEqual(result.output_filename, "product-module-branch-v1-20260610.log")
        self.assertEqual(result.lines_to_save, [
            "2026-06-07 12:30:45 ERROR target",
            "2026-06-07 12:30:46 INFO target context",
            "    at demo.Target.run(Target.java:42)",
        ])
        self.assertTrue(result.metadata["date_filter_applied"])
        self.assertEqual(result.metadata["target_date"], "2026-06-07")
        self.assertEqual(result.metadata["original_line_count"], 6)
        self.assertEqual(result.metadata["filtered_line_count"], 3)
        self.assertEqual(result.metadata["matched_line_count"], 2)

    def test_prepares_upload_without_date_filter_keeps_full_log_context(self):
        routes = load_routes_module()
        payload = "\n".join([
            "2026-06-07 12:30:44 INFO request started",
            "2026-06-07 12:30:45 WARN redis latency is high",
            "2026-06-07 12:30:46 ERROR target failure",
            "    at demo.Target.run(Target.java:42)",
            "2026-06-07 12:30:47 INFO request finished",
        ])
        uploaded_file = UploadedFileStub(payload.encode("utf-8"))

        result = routes.prepare_uploaded_log(
            uploaded_file=uploaded_file,
            original_filename="server.log",
            log_name="product-module-branch-v1-20260610.log",
            date_filter="",
        )

        self.assertEqual(result.lines_to_save, payload.splitlines())
        self.assertFalse(result.metadata["date_filter_applied"])
        self.assertEqual(result.metadata["original_line_count"], 5)
        self.assertEqual(result.metadata["filtered_line_count"], 5)

    def test_upload_image_names_include_unique_suffix_and_original_extension(self):
        routes = load_routes_module()

        first_name = routes.build_upload_image_name(
            "product",
            "module",
            "https://code.example/group/repo.git",
            "master",
            "error-screen.png",
        )
        second_name = routes.build_upload_image_name(
            "product",
            "module",
            "https://code.example/group/repo.git",
            "master",
            "error-screen.png",
        )

        self.assertNotEqual(first_name, second_name)
        self.assertTrue(first_name.endswith(".png"))
        self.assertIn("product-module-", first_name)

    def test_supported_image_filename_accepts_png_jpg_and_rejects_gif(self):
        routes = load_routes_module()

        self.assertTrue(routes.is_supported_image_filename("a.png"))
        self.assertTrue(routes.is_supported_image_filename("a.jpg"))
        self.assertTrue(routes.is_supported_image_filename("a.jpeg"))
        self.assertFalse(routes.is_supported_image_filename("a.gif"))

    def test_prepare_uploaded_images_saves_multiple_images(self):
        routes = load_routes_module()

        result = routes.prepare_uploaded_images(
            [
                ImageFileStub("query.png", make_image_bytes("PNG")),
                ImageFileStub("error.jpg", make_image_bytes("JPEG")),
            ],
            product_name="product",
            module_name="module",
            address="https://code.example/group/repo.git",
            tag_version="master",
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["sequence"], 1)
        self.assertEqual(result[1]["sequence"], 2)
        self.assertTrue(result[0]["file_path"].endswith(".png"))
        self.assertTrue(result[1]["file_path"].endswith(".jpg"))
        self.assertEqual(result[0]["original_filename"], "query.png")

    def test_prepare_uploaded_images_removes_earlier_files_when_later_save_fails(self):
        routes = load_routes_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            first_path = Path(temp_dir) / "first.png"
            calls = []

            def save_with_failure(file_bytes, filename):
                calls.append(filename)
                if len(calls) == 2:
                    raise OSError("disk full")
                first_path.write_bytes(file_bytes)
                return str(first_path)

            routes.save_binary_upload_file = save_with_failure

            with self.assertRaisesRegex(OSError, "disk full"):
                routes.prepare_uploaded_images(
                    [
                        ImageFileStub("first.png", make_image_bytes("PNG")),
                        ImageFileStub("second.png", make_image_bytes("PNG")),
                    ],
                    product_name="product",
                    module_name="module",
                    address="https://code.example/group/repo.git",
                    tag_version="master",
                )

            self.assertFalse(first_path.exists())


if __name__ == "__main__":
    unittest.main()

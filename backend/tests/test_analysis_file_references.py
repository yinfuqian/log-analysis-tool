import os
import tempfile
import unittest
from pathlib import Path

from app.uploads.references import AnalysisInputError, require_path_under, resolve_analysis_inputs


class Record:
    def __init__(self, record_id, path):
        self.id = record_id
        self.log_file_path = str(path)


class AnalysisFileReferenceTests(unittest.TestCase):
    def test_rejects_existing_file_outside_upload_root_without_leaking_path(self):
        with tempfile.TemporaryDirectory() as upload_dir, tempfile.NamedTemporaryFile() as outside:
            with self.assertRaises(AnalysisInputError) as raised:
                require_path_under(outside.name, upload_dir)

            self.assertNotIn(outside.name, str(raised.exception))

    def test_rejects_upload_root_prefix_collision(self):
        with tempfile.TemporaryDirectory() as parent:
            upload_dir = Path(parent) / "upload"
            collision = Path(parent) / "upload-evil" / "file.log"
            upload_dir.mkdir()
            collision.parent.mkdir()
            collision.write_text("error", encoding="utf-8")

            with self.assertRaises(AnalysisInputError):
                require_path_under(collision, upload_dir)

    def test_resolves_single_and_multiple_database_ids(self):
        with tempfile.TemporaryDirectory() as upload_dir:
            first = Path(upload_dir) / "first.log"
            second = Path(upload_dir) / "second.png"
            first.write_text("error", encoding="utf-8")
            second.write_bytes(b"image")
            records = {1: Record(1, first), 2: Record(2, second)}

            data = {"log_ids": [1, 2], "source_type": "image"}
            paths = resolve_analysis_inputs(data, upload_dir, records.get)

            self.assertEqual(paths, [str(first.resolve()), str(second.resolve())])
            self.assertEqual(data["file_path"], str(first.resolve()))
            self.assertEqual(data["file_paths"], paths)

    def test_legacy_path_must_match_a_database_record(self):
        with tempfile.TemporaryDirectory() as upload_dir:
            path = Path(upload_dir) / "legacy.log"
            path.write_text("error", encoding="utf-8")

            with self.assertRaisesRegex(AnalysisInputError, "上传记录"):
                resolve_analysis_inputs({"file_path": str(path)}, upload_dir, lambda _key: None)


if __name__ == "__main__":
    unittest.main()

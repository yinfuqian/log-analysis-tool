import tempfile
import unittest
from pathlib import Path


class FakePaddleEngine:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def predict(self, input_path):
        self.calls.append(input_path)
        return [self.results[len(self.calls) - 1]]


class ImageOcrTests(unittest.TestCase):
    def test_python_313_runtime_is_rejected_before_loading_native_ocr(self):
        from app.analysis.image_ocr import ensure_supported_runtime

        with self.assertRaisesRegex(RuntimeError, "Python 3.10"):
            ensure_supported_runtime((3, 13))

    def test_returns_unavailable_when_all_existing_images_fail_prediction(self):
        from app.analysis.image_ocr import extract_text_from_images

        class FailingEngine:
            def predict(self, _image):
                raise RuntimeError("std::exception")

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "screen.png"
            path.write_bytes(b"image")
            result = extract_text_from_images(
                [str(path)],
                engine=FailingEngine(),
                image_preprocessor=lambda value: value,
            )

        self.assertFalse(result["available"])
        self.assertEqual(result["extracted_text"], "")
        self.assertIn("std::exception", result["warnings"][0])

    def test_preprocessed_screenshot_keeps_three_color_channels_for_paddle(self):
        import cv2
        import numpy as np

        from app.analysis.image_ocr import preprocess_screenshot

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "screen.png"
            image = np.zeros((120, 320, 3), dtype=np.uint8)
            cv2.putText(image, "ERROR", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 2)
            self.assertTrue(cv2.imwrite(str(path), image))

            processed = preprocess_screenshot(str(path))

        self.assertEqual(len(processed.shape), 3)
        self.assertEqual(processed.shape[2], 3)

    def test_combines_multiple_images_and_filters_low_confidence_lines(self):
        from app.analysis.image_ocr import extract_text_from_images

        engine = FakePaddleEngine([
            {
                "rec_texts": [
                    "2026-07-14 ERROR downstream request failed",
                    "unreliable fragment",
                ],
                "rec_scores": [0.98, 0.20],
                "rec_polys": [
                    [[10, 10], [400, 10], [400, 30], [10, 30]],
                    [[10, 40], [220, 40], [220, 60], [10, 60]],
                ],
            },
            {
                "rec_texts": [
                    "java.lang.NullPointerException: null",
                    "at demo.Service.run(Service.java:42)",
                ],
                "rec_scores": [0.96, 0.94],
                "rec_polys": [
                    [[10, 10], [360, 10], [360, 30], [10, 30]],
                    [[10, 40], [390, 40], [390, 60], [10, 60]],
                ],
            },
        ])

        with tempfile.TemporaryDirectory() as temp_dir:
            paths = []
            for name in ("first.png", "second.png"):
                path = Path(temp_dir) / name
                path.write_bytes(b"fake image content")
                paths.append(str(path))
            result = extract_text_from_images(
                paths,
                engine=engine,
                min_confidence=0.45,
                image_preprocessor=lambda path: path,
            )

        self.assertTrue(result["available"])
        self.assertEqual(result["engine"], "paddleocr")
        self.assertEqual(len(result["lines"]), 3)
        self.assertNotIn("unreliable fragment", result["extracted_text"])
        self.assertEqual(
            result["extracted_text"].splitlines(),
            [
                "2026-07-14 ERROR downstream request failed",
                "java.lang.NullPointerException: null",
                "at demo.Service.run(Service.java:42)",
            ],
        )
        self.assertEqual([line["image_index"] for line in result["lines"]], [0, 1, 1])
        self.assertAlmostEqual(result["average_confidence"], 0.96, places=2)

    def test_returns_unavailable_result_when_runtime_cannot_initialize(self):
        from app.analysis.image_ocr import extract_text_from_images

        def fail_factory():
            raise ImportError("paddleocr is not installed")

        result = extract_text_from_images(
            ["missing.png"],
            engine_factory=fail_factory,
        )

        self.assertFalse(result["available"])
        self.assertEqual(result["extracted_text"], "")
        self.assertEqual(result["lines"], [])
        self.assertIn("paddleocr is not installed", result["warnings"][0])


if __name__ == "__main__":
    unittest.main()

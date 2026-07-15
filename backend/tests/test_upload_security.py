import io
import unittest

from PIL import Image

from app.uploads.validation import (
    UploadValidationError,
    read_upload_bytes,
    validate_image_count,
    validate_image_upload,
)


def make_image_bytes(image_format="PNG", size=(8, 8)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color="white").save(buffer, format=image_format)
    return buffer.getvalue()


class UploadSecurityTests(unittest.TestCase):
    def test_rejects_log_larger_than_configured_limit(self):
        with self.assertRaisesRegex(UploadValidationError, "大小") as raised:
            read_upload_bytes(io.BytesIO(b"12345"), max_bytes=4, label="日志文件")

        self.assertEqual(raised.exception.status_code, 413)

    def test_rejects_more_than_ten_images(self):
        with self.assertRaises(UploadValidationError) as raised:
            validate_image_count([object()] * 11, max_count=10)

        self.assertEqual(raised.exception.status_code, 413)

    def test_rejects_image_larger_than_configured_limit(self):
        payload = make_image_bytes()

        with self.assertRaises(UploadValidationError) as raised:
            validate_image_upload("screen.png", io.BytesIO(payload), max_bytes=len(payload) - 1)

        self.assertEqual(raised.exception.status_code, 413)

    def test_rejects_forged_image_extension(self):
        with self.assertRaisesRegex(UploadValidationError, "格式"):
            validate_image_upload("screen.jpg", io.BytesIO(make_image_bytes("PNG")))

    def test_rejects_non_image_payload_with_supported_extension(self):
        with self.assertRaisesRegex(UploadValidationError, "有效图片"):
            validate_image_upload("screen.png", io.BytesIO(b"not-an-image"))

    def test_rejects_image_exceeding_pixel_limit(self):
        with self.assertRaisesRegex(UploadValidationError, "像素") as raised:
            validate_image_upload(
                "screen.png",
                io.BytesIO(make_image_bytes(size=(11, 10))),
                max_pixels=100,
            )

        self.assertEqual(raised.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()

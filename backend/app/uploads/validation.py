"""validation 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError


IMAGE_FORMATS_BY_EXTENSION = {
    ".png": "PNG",
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
}


class UploadValidationError(ValueError):
    """UploadValidationError 类封装该领域对象的状态、依赖与相关行为。"""
    def __init__(self, message, status_code=400):
        """初始化当前对象的依赖、界面状态或运行参数。"""
        super().__init__(message)
        self.status_code = status_code


def read_upload_bytes(stream, max_bytes, label="文件", chunk_size=1024 * 1024):
    """读取并返回 read_upload_bytes 对应的业务数据，保持现有调用约定。"""
    try:
        stream.seek(0)
    except (AttributeError, OSError):
        pass

    chunks = []
    total = 0
    while True:
        chunk = stream.read(min(chunk_size, max_bytes + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadValidationError(f"{label}大小超过限制", status_code=413)
        chunks.append(chunk)
    return b"".join(chunks)


def validate_image_count(uploaded_files, max_count):
    """校验 validate_image_count 对应的业务数据，保持现有调用约定。"""
    count = len(uploaded_files or [])
    if count > max_count:
        raise UploadValidationError(f"单次最多上传 {max_count} 张图片", status_code=413)


def validate_image_upload(filename, stream, max_bytes=10 * 1024 * 1024, max_pixels=40_000_000):
    """校验 validate_image_upload 对应的业务数据，保持现有调用约定。"""
    extension = Path(str(filename or "")).suffix.lower()
    expected_format = IMAGE_FORMATS_BY_EXTENSION.get(extension)
    if not expected_format:
        raise UploadValidationError("仅支持 png/jpg/jpeg 图片格式")

    payload = read_upload_bytes(stream, max_bytes=max_bytes, label="图片")
    if not payload:
        raise UploadValidationError("图片内容为空")

    try:
        with Image.open(io.BytesIO(payload)) as image:
            actual_format = image.format
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise UploadValidationError("上传内容不是有效图片") from exc

    if actual_format != expected_format:
        raise UploadValidationError("图片扩展名与实际格式不一致")
    if width <= 0 or height <= 0 or width * height > max_pixels:
        raise UploadValidationError("图片像素数量超过限制", status_code=413)
    return payload

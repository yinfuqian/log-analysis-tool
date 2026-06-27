import gzip
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta


class LogProcessingError(ValueError):
    pass


@dataclass
class DateFilterResult:
    filtered_lines: list[str]
    date_filter_applied: bool
    target_date: date | None
    original_line_count: int
    filtered_line_count: int
    matched_line_count: int
    warning: str | None = None


TIMESTAMP_PATTERNS = [
    re.compile(r"\[?(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:Z)?\]?"),
    re.compile(r"\[?(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?\]?"),
    re.compile(r"\[?(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\]?"),
]


def read_uploaded_log_lines(uploaded_file, filename: str) -> list[str]:
    raw_content = _read_uploaded_bytes(uploaded_file)
    if filename.lower().endswith(".gz"):
        try:
            raw_content = gzip.decompress(raw_content)
        except OSError as exc:
            raise LogProcessingError("gz 文件损坏或无法解压") from exc

    return _decode_log_bytes(raw_content).splitlines()


def resolve_target_date(date_filter: str | None, today: date | None = None) -> date | None:
    if date_filter is None or not str(date_filter).strip():
        return None

    value = str(date_filter).strip()
    today = today or date.today()

    if re.fullmatch(r"[+-]?\d+", value):
        return today + timedelta(days=int(value))

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise LogProcessingError("日期格式非法，请输入 -3 或 2026-06-07") from exc


def extract_log_date(line: str) -> date | None:
    for pattern in TIMESTAMP_PATTERNS:
        match = pattern.search(line)
        if not match:
            continue
        try:
            return date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError:
            continue
    return None


def filter_lines_by_date(lines: list[str], target_date: date | None) -> DateFilterResult:
    normalized_lines = [line.rstrip("\r\n") for line in lines]
    original_line_count = len(normalized_lines)

    if target_date is None:
        return DateFilterResult(
            filtered_lines=normalized_lines,
            date_filter_applied=False,
            target_date=None,
            original_line_count=original_line_count,
            filtered_line_count=original_line_count,
            matched_line_count=0,
        )

    extracted_dates = [extract_log_date(line) for line in normalized_lines]
    if not any(extracted_dates):
        return DateFilterResult(
            filtered_lines=normalized_lines,
            date_filter_applied=False,
            target_date=target_date,
            original_line_count=original_line_count,
            filtered_line_count=original_line_count,
            matched_line_count=0,
            warning="没有识别到可用于日期过滤的时间戳，已保留全部日志内容",
        )

    filtered_lines = []
    current_event_matches = False
    matched_line_count = 0

    for line, line_date in zip(normalized_lines, extracted_dates):
        if line_date is not None:
            current_event_matches = line_date == target_date
            if current_event_matches:
                filtered_lines.append(line)
                matched_line_count += 1
            continue

        if current_event_matches:
            filtered_lines.append(line)

    warning = None
    if matched_line_count == 0:
        warning = "指定日期没有匹配到日志内容"

    return DateFilterResult(
        filtered_lines=filtered_lines,
        date_filter_applied=True,
        target_date=target_date,
        original_line_count=original_line_count,
        filtered_line_count=len(filtered_lines),
        matched_line_count=matched_line_count,
        warning=warning,
    )


def _read_uploaded_bytes(uploaded_file) -> bytes:
    stream = getattr(uploaded_file, "stream", None)
    if stream is not None:
        try:
            stream.seek(0)
        except (AttributeError, OSError):
            pass
        return stream.read()

    try:
        uploaded_file.seek(0)
    except (AttributeError, OSError):
        pass
    return uploaded_file.read()


def _decode_log_bytes(raw_content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return raw_content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_content.decode("utf-8", errors="ignore")

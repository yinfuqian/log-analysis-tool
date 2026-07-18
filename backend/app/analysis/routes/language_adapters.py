"""language adapters 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
import os
import re


PYTHON_FRAME_PATTERN = re.compile(
    r'File\s+"([^"]+)",\s+line\s+(\d+)(?:,\s+in\s+([^\n]+))?'
)
GO_FRAME_PATTERN = re.compile(
    r'(?m)^\s+([^\s]+\.go):(\d+)(?:\s+\+0x[0-9a-fA-F]+)?'
)
SHELL_FRAME_PATTERN = re.compile(
    r'(?m)([^\s:]+\.(?:sh|bash|zsh))(?::\s*line\s+|:)(\d+)'
)
JAVA_FRAME_PATTERN = re.compile(
    r'(?m)^\s*at\s+([\w.$<>]+)\(([^():]+\.(?:java|kt|groovy)):(\d+)\)'
)


def _extract_error_descriptor(text):
    """解析或提取并返回 _extract_error_descriptor 对应的业务数据，保持现有调用约定。"""
    exception_matches = re.findall(
        r'(?m)^\s*([A-Za-z_][\w.$]*(?:Exception|Error)):\s*(.*)$',
        text,
    )
    if exception_matches:
        error_type, message = exception_matches[-1]
        return error_type, message.strip()

    panic_matches = re.findall(r'(?m)^\s*(panic):\s*(.*)$', text, re.IGNORECASE)
    if panic_matches:
        error_type, message = panic_matches[-1]
        return error_type.lower(), message.strip()

    shell_match = re.search(
        r'(?mi)^.*(?:command not found|exit status\s+\d+|permission denied|no such file or directory).*$' ,
        text,
    )
    if shell_match:
        return "ShellError", shell_match.group(0).strip()

    generic_match = re.search(r'(?mi)^.*\b(?:ERROR|FATAL)\b.*$', text)
    if generic_match:
        return "Error", generic_match.group(0).strip()
    return "UnknownError", "unknown error"


def extract_source_locations(log_content):
    """解析或提取并返回 extract_source_locations 对应的业务数据，保持现有调用约定。"""
    text = str(log_content or "")
    error_type, message = _extract_error_descriptor(text)
    locations = []
    seen = set()

    def add(language, file_name, line_number, symbol=""):
        """处理 add 对应的业务步骤，并向调用方返回所需结果。"""
        base_name = os.path.basename(str(file_name).replace("\\", "/"))
        key = (language, base_name, int(line_number), symbol or "")
        if key in seen:
            return
        seen.add(key)
        locations.append({
            "language": language,
            "file": base_name,
            "line": int(line_number),
            "symbol": str(symbol or "").strip(),
            "error_type": error_type,
            "message": message,
            "error": f"{error_type}: {message}",
        })

    for file_name, line_number, symbol in PYTHON_FRAME_PATTERN.findall(text):
        add("python", file_name, line_number, symbol)
    for file_name, line_number in GO_FRAME_PATTERN.findall(text):
        add("go", file_name, line_number)
    for file_name, line_number in SHELL_FRAME_PATTERN.findall(text):
        add("shell", file_name, line_number)
    for symbol, file_name, line_number in JAVA_FRAME_PATTERN.findall(text):
        add("java", file_name, line_number, symbol)
    return locations


def detect_log_languages(log_content):
    """处理 detect_log_languages 对应的业务步骤，并向调用方返回所需结果。"""
    languages = []
    seen = set()
    for location in extract_source_locations(log_content):
        language = location.get("language")
        if language and language not in seen:
            seen.add(language)
            languages.append(language)
    return languages

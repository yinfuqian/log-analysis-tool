import re
from flask import current_app as app
from app.config import Config


def extract_code_positions(log_content):
    LOG_CODE_PATTERNS = app.config.get("LOG_CODE_PATTERNS")
    """
    从日志中提取类路径和对应的行号
    :param log_content: 日志文本
    :return: List[Tuple[class_path, line_number]]
    """
    matches = []
    for pattern in LOG_CODE_PATTERNS:
        for match in re.findall(pattern, log_content):
            if len(match) == 3:
                class_path, _, line = match
                matches.append((class_path, int(line)))
    return matches

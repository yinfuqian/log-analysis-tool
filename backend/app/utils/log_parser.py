"""log parser 模块负责本文件相关的业务流程、数据转换与依赖协作。"""
import re
from flask import current_app as app
from app.config import Config


def extract_code_positions(log_content):
    """解析或提取并返回 extract_code_positions 对应的业务数据，保持现有调用约定。"""
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

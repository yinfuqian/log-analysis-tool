"""registry 模块负责发现与解析技能目录中的 Codex Skill 定义，供执行接口按 skill_id 定位技能。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


# 技能标识只允许小写字母、数字、点、下划线与连字符，避免出现路径穿越或非法目录名。
SKILL_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SKILL_FILE_NAME = "SKILL.md"
RUNTIME_FILE_NAME = "runtime.json"
DEFAULT_TIMEOUT_SECONDS = 1800


class SkillError(Exception):
    """技能相关错误的基础异常类型。"""


class SkillNotFoundError(SkillError):
    """指定的技能在技能目录中不存在时抛出的异常。"""


class SkillDefinitionError(SkillError):
    """技能目录结构或元数据不合法时抛出的异常。"""


def _strip_quotes(value: str) -> str:
    """去掉配置值两侧成对的单引号或双引号。"""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def _strip_block_indicator(value: str) -> str:
    """去掉 YAML 块标量指示符（>、| 及其 +/- 结尾变体），只保留真正的值。"""
    text = value.strip()
    if text and text[0] in (">", "|"):
        return text[1:].lstrip("+-").strip()
    return text


def parse_front_matter(text: str) -> dict:
    """解析 SKILL.md 顶部的 front matter，返回 name、description 等元数据。"""
    lines = str(text or "").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    metadata: dict = {}
    current_key = None
    for raw_line in lines[1:]:
        if raw_line.strip() == "---":
            break
        if not raw_line.strip():
            continue
        # 缩进行视为上一个键的续行，用于兼容多行 description。
        if raw_line[:1] in (" ", "\t") and current_key:
            metadata[current_key] = f"{metadata.get(current_key, '')} {raw_line.strip()}".strip()
            continue
        key, separator, value = raw_line.partition(":")
        if not separator:
            continue
        current_key = key.strip()
        metadata[current_key] = _strip_block_indicator(_strip_quotes(value))
    return metadata


@dataclass(frozen=True)
class SkillDefinition:
    """描述一个可执行技能的关键元数据与可选的运行参数。"""

    skill_id: str
    name: str
    description: str
    directory: str
    prompt_template: str = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    required_inputs: tuple = ()

    def to_dict(self) -> dict:
        """转换为接口返回用的字典结构。"""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "description": self.description,
            "directory": self.directory,
            "timeout_seconds": self.timeout_seconds,
            "required_inputs": list(self.required_inputs),
        }


def _load_runtime(directory: Path) -> dict:
    """读取技能目录下可选的 runtime.json，用于覆盖提示词模板与超时时间。"""
    runtime_file = directory / RUNTIME_FILE_NAME
    if not runtime_file.is_file():
        return {}
    try:
        payload = json.loads(runtime_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SkillDefinitionError(f"技能运行配置无法解析：{runtime_file}") from exc
    if not isinstance(payload, dict):
        raise SkillDefinitionError(f"技能运行配置必须是 JSON 对象：{runtime_file}")
    return payload


def _normalize_timeout(value, fallback: int) -> int:
    """把技能自定义超时时间规范化为正整数秒。"""
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        return fallback
    return timeout if timeout > 0 else fallback


def load_skill(directory, skill_id: str = None) -> SkillDefinition:
    """读取单个技能目录，解析 SKILL.md 与 runtime.json 后返回技能定义。"""
    skill_directory = Path(directory)
    skill_file = skill_directory / SKILL_FILE_NAME
    if not skill_file.is_file():
        raise SkillNotFoundError(f"技能目录缺少 {SKILL_FILE_NAME}：{skill_directory}")

    metadata = parse_front_matter(skill_file.read_text(encoding="utf-8", errors="replace"))
    resolved_id = str(skill_id or metadata.get("name") or skill_directory.name).strip()
    if not SKILL_ID_PATTERN.match(resolved_id):
        raise SkillDefinitionError(f"技能标识不合法：{resolved_id}")

    runtime = _load_runtime(skill_directory)
    prompt_template = runtime.get("prompt_template")
    if prompt_template is not None and not str(prompt_template).strip():
        prompt_template = None

    required_inputs = runtime.get("required_inputs") or ()
    if isinstance(required_inputs, str):
        required_inputs = [required_inputs]
    normalized_required = tuple(
        str(item).strip() for item in required_inputs if str(item or "").strip()
    )

    return SkillDefinition(
        skill_id=resolved_id,
        name=str(metadata.get("name") or resolved_id),
        description=str(metadata.get("description") or "").strip(),
        directory=str(skill_directory),
        prompt_template=str(prompt_template) if prompt_template else None,
        timeout_seconds=_normalize_timeout(runtime.get("timeout_seconds"), DEFAULT_TIMEOUT_SECONDS),
        required_inputs=normalized_required,
    )


def list_skills(skills_dir) -> list:
    """扫描技能根目录，返回全部可用技能的定义列表。"""
    root = Path(skills_dir)
    if not root.is_dir():
        return []

    skills = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or child.name.startswith((".", "_")):
            continue
        if not SKILL_ID_PATTERN.match(child.name):
            continue
        if not (child / SKILL_FILE_NAME).is_file():
            continue
        try:
            skills.append(load_skill(child, child.name))
        except SkillError:
            # 单个技能目录损坏不影响其余技能被发现。
            continue
    return skills


def resolve_skill(skills_dir, skill_id: str) -> SkillDefinition:
    """按 skill_id 定位技能目录，并拒绝任何越出技能根目录的路径。"""
    normalized = str(skill_id or "").strip()
    if not SKILL_ID_PATTERN.match(normalized):
        raise SkillDefinitionError(f"技能标识不合法：{normalized or '(空)'}")

    root = Path(skills_dir).resolve()
    target = (root / normalized).resolve()
    if target != root and root not in target.parents:
        raise SkillDefinitionError(f"技能路径越界：{normalized}")
    if not target.is_dir():
        raise SkillNotFoundError(f"技能不存在：{normalized}")
    return load_skill(target, normalized)

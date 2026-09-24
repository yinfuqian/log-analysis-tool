#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
探测项目基本信息：技术栈、REPO_GROUP、模块名、是否存在旧版流水线文件。
输出 JSON 格式，供 pipeline-adapter skill 快速决策使用。
兼容 Python 2.7 和 Python 3。
"""

from __future__ import print_function
import io
import json
import os
import re
import sys


def _read_file(path):
    """读取文件内容为 unicode 字符串。"""
    try:
        with io.open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def detect_framework(root):
    """根据特征文件识别技术栈。"""
    if os.path.exists(os.path.join(root, "go.mod")):
        return "go"
    if os.path.exists(os.path.join(root, "pom.xml")):
        return "java"
    if os.path.exists(os.path.join(root, "package.json")):
        return "web"
    if os.path.exists(os.path.join(root, "requirements.txt")):
        return "python"
    if os.path.exists(os.path.join(root, "CMakeLists.txt")):
        return "cpp"
    # python 兜底检测：递归查找 .py 文件（仅查一层子目录以控制性能）
    for entry in os.listdir(root):
        full = os.path.join(root, entry)
        if os.path.isdir(full):
            for sub in os.listdir(full):
                if sub.endswith(".py"):
                    return "python"
        elif entry.endswith(".py"):
            return "python"
    return "unknown"


def detect_repo_group(root):
    """按优先级推断仓库所属组 REPO_GROUP。"""
    # 1. git remote url
    git_config = os.path.join(root, ".git", "config")
    if os.path.exists(git_config):
        content = _read_file(git_config)
        m = re.search(r'url\s*=\s*[^\s]+/([^/\s]+)/[^/\s]+\.git', content)
        if m:
            return m.group(1)
        m = re.search(r'url\s*=\s*[^\s]+[:/]([^/\s]+)/[^/\s]+', content)
        if m:
            return m.group(1)

    # 2. go.mod
    go_mod = os.path.join(root, "go.mod")
    if os.path.exists(go_mod):
        content = _read_file(go_mod)
        m = re.search(r'module\s+([\w.]+)/([^/\s]+)/([^/\s]+)', content)
        if m:
            return m.group(2)

    # 3. pom.xml
    pom_xml = os.path.join(root, "pom.xml")
    if os.path.exists(pom_xml):
        content = _read_file(pom_xml)
        m = re.search(r'<groupId>([^<]+)</groupId>', content)
        if m:
            parts = m.group(1).split(".")
            if len(parts) >= 2:
                return parts[1]
            return parts[0]

    return None


def detect_module_name(root):
    """推断模块名/仓库名。"""
    # 1. git remote url
    git_config = os.path.join(root, ".git", "config")
    if os.path.exists(git_config):
        content = _read_file(git_config)
        m = re.search(r'url\s*=\s*[^\s]+/([^/\s]+)/([^/\s]+)\.git', content)
        if m:
            return m.group(2)
        m = re.search(r'url\s*=\s*[^\s]+[:/]([^/\s]+)/([^/\s]+)', content)
        if m:
            return m.group(2)

    # 2. go.mod
    go_mod = os.path.join(root, "go.mod")
    if os.path.exists(go_mod):
        content = _read_file(go_mod)
        m = re.search(r'module\s+([\w.]+)/([^/\s]+)/([^/\s]+)', content)
        if m:
            return m.group(3)

    # 3. 目录名称
    return os.path.basename(os.path.abspath(root))


def _list_files_in_dir(path):
    """列出目录下所有文件（非递归），返回完整路径列表。"""
    if not os.path.isdir(path):
        return []
    return [os.path.join(path, f) for f in os.listdir(path)]


def has_legacy_files(root):
    """检查是否存在旧版流水线文件及特征。"""
    app_json = os.path.join(root, "app.json")
    docker_compose = os.path.join(root, "docker-compose.yml")
    k8s_dir = os.path.join(root, "deployments", "kubernetes")

    result = {
        "has_app_json": os.path.exists(app_json),
        "has_docker_compose": os.path.exists(docker_compose),
        "has_k8s_yaml": False,
        "legacy_app_json_features": {},
        "legacy_docker_compose_features": {},
        "legacy_k8s_features": {},
    }

    # 检查 K8S deployment 是否存在
    if os.path.isdir(k8s_dir):
        for f in _list_files_in_dir(k8s_dir):
            if os.path.isfile(f) and f.endswith(".yaml") and "_deployment" in os.path.basename(f):
                result["has_k8s_yaml"] = True
                break

    # 检查 app.json 旧版特征
    if os.path.exists(app_json):
        try:
            data = json.loads(_read_file(app_json))
            spec = {}
            apps = data.get("applications", [{}]) if isinstance(data.get("applications"), list) else [{}]
            containers = apps[0].get("containers", [{}]) if isinstance(apps[0].get("containers"), list) else [{}]
            specs = containers[0].get("spec", [{}]) if isinstance(containers[0].get("spec"), list) else [{}]
            spec = specs[0] if specs and isinstance(specs[0], dict) else {}
            if isinstance(spec, dict):
                result["legacy_app_json_features"]["inline_healthcheck"] = (
                    "healthcheck" in spec and "healthcheck_ref" not in spec
                )
                result["legacy_app_json_features"]["inline_volumes"] = (
                    "volumes" in spec and "volumes_ref" not in spec
                )
                result["legacy_app_json_features"]["inline_resources"] = (
                    "resources" in spec and "resources_ref" not in spec
                )
                result["legacy_app_json_features"]["inline_ports"] = (
                    "ports" in spec and "ports_ref" not in spec
                )
                result["legacy_app_json_features"]["runtime_interpreter_misplaced"] = (
                    "runtime-interpreter" in data
                )
        except Exception:
            pass

    # 检查 docker-compose
    if os.path.exists(docker_compose):
        content = _read_file(docker_compose)
        env_section = re.search(r'environment:\s*\n((?:\s+-?\s*\S+.*\n)+)', content)
        has_env = False
        if env_section:
            for line in env_section.group(1).split("\n"):
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    has_env = True
                    break
        result["legacy_docker_compose_features"]["has_environment_values"] = has_env

    # 检查 K8S deployment/configmap
    if os.path.isdir(k8s_dir):
        has_configmap = False
        for f in _list_files_in_dir(k8s_dir):
            basename = os.path.basename(f)
            if "_config-map" in basename or "_config_map" in basename:
                has_configmap = True
                break
        result["legacy_k8s_features"]["has_config_map_yaml"] = has_configmap

        for f in _list_files_in_dir(k8s_dir):
            basename = os.path.basename(f)
            if "_deployment" in basename and f.endswith(".yaml"):
                content = _read_file(f)
                result["legacy_k8s_features"]["deployment_has_env_content"] = bool(
                    re.search(r'env:\s*\n\s+-\s+name:', content)
                )
                result["legacy_k8s_features"]["deployment_has_resources_content"] = bool(
                    re.search(r'resources:\s*\n\s+(?:limits|requests):', content)
                )
                break

    result["is_legacy_project"] = (
        any(result["legacy_app_json_features"].values())
        or result["legacy_docker_compose_features"].get("has_environment_values", False)
        or result["legacy_k8s_features"].get("has_config_map_yaml", False)
        or result["legacy_k8s_features"].get("deployment_has_env_content", False)
        or result["legacy_k8s_features"].get("deployment_has_resources_content", False)
    )

    return result


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    framework = detect_framework(root)
    repo_group = detect_repo_group(root)
    module_name = detect_module_name(root)
    legacy = has_legacy_files(root)

    result = {
        "framework": framework,
        "module_name": module_name,
        "repo_group": repo_group,
        "legacy": legacy,
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

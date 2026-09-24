#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
生成符合 CI v3 规范的 app.json。
支持新项目生成和旧版升级（自动读取旧配置并迁移）。
兼容 Python 2.7 和 Python 3。
"""

from __future__ import print_function
import argparse
import io
import json
import os
import re
import sys


def _read_file(path):
    try:
        with io.open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _load_json(path):
    try:
        with io.open(path, encoding="utf-8", errors="ignore") as f:
            return json.load(f)
    except Exception:
        return None


def _write_file(path, content):
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(content)


def get_skill_dir():
    """获取 pipeline-adapter skill 的根目录（脚本位于 scripts/ 下）。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_template(skill_dir):
    path = os.path.join(skill_dir, "assets", "templates", "app.json")
    raw = _read_file(path)
    if not raw:
        raise RuntimeError("模板文件不存在: " + path)
    return raw


def replace_placeholders(text, ctx):
    """替换模板中的占位符。"""
    module_name = ctx.get("module_name", "")
    repo_group = ctx.get("repo_group", "")
    server_port = str(ctx.get("server_port", 8080))
    exposed_port = str(ctx.get("exposed_port", 48080))

    repo_name = module_name
    module_group = repo_group.replace("-", "/") if repo_group else ""
    module_name_upper = module_name.replace("-", "_").upper()
    module_name_upper_hyphen = module_name.upper()
    working_dir_var = "$" + module_name_upper_hyphen + "_WORKING_DIR"
    image_tag_var = "$" + module_name_upper_hyphen + "_IMAGE_TAG"

    text = text.replace("{{MODULE_NAME}}", module_name)
    text = text.replace("{{MODULE_GROUP}}", module_group)
    text = text.replace("{{REPO_NAME}}", repo_name)
    text = text.replace("{{REPO_GROUP}}", repo_group)
    text = text.replace("{{MODULE_NAME_UPPER}}", module_name_upper)
    text = text.replace("{{MODULE_NAME_UPPER_HYPHEN}}", module_name_upper_hyphen)
    text = text.replace("{{MODULE_NAME_UPPER_HYPHEN_WORKING_DIR}}", working_dir_var)
    text = text.replace("{{MODULE_NAME_UPPER_HYPHEN_IMAGE_TAG}}", image_tag_var)
    text = text.replace("{{SERVER_PORT}}", server_port)
    text = text.replace("{{EXPOSED_PORT}}", exposed_port)
    return text


def adjust_for_framework(data, framework):
    """根据技术栈调整 runtime-interpreter。"""
    interpreters = []
    if framework == "java":
        interpreters.append({"name": "jdk", "version": "1.8", "type": "JavaRunTimeEnv"})
    elif framework == "web":
        interpreters.append({"name": "nginx", "version": "1.23", "type": "ReverseProxy"})
        # Web 前端默认 readinessProbe 用 tcpSocket，livenessProbe 用 httpGet /
        # 两者不能完全相同
        for hc_group in data.get("healthcheck", []):
            for p in hc_group.get("data", []):
                if p.get("name") in ("readinessProbe", "startupProbe"):
                    p["type"] = "tcpSocket"
                    p.pop("path", None)
                elif p.get("name") == "livenessProbe":
                    p["type"] = "httpGet"
                    p["path"] = "/"
    elif framework == "python":
        interpreters.append({"name": "python", "version": "3.8", "type": "PythonInterpreter"})

    if not interpreters:
        return data

    for app in data.get("applications", []):
        for container in app.get("containers", []):
            for spec in container.get("spec", []):
                existing = spec.get("runtime-interpreter", [])
                if not isinstance(existing, list):
                    existing = []
                # 去重：若已有同名 interpreter 则跳过
                for item in interpreters:
                    if not any(e.get("name") == item["name"] for e in existing):
                        existing.append(item)
                spec["runtime-interpreter"] = existing
    return data


def adjust_scope(data, orchestration_type):
    """根据部署方式调整 scope。"""
    scope_map = {
        "docker-compose": "paas",
        "kubernetes": "kubernetes",
        "docker-compose-and-kubernetes": "all",
        "none": "all",
    }
    scope = scope_map.get(orchestration_type, "all")

    for app in data.get("applications", []):
        app["scope"] = scope
        for container in app.get("containers", []):
            for spec in container.get("spec", []):
                spec["scope"] = scope

    for env in data.get("environments", []):
        env["scope"] = scope

    return data


def _ensure_list(obj):
    return obj if isinstance(obj, list) else []


def _ensure_dict(obj):
    return obj if isinstance(obj, dict) else {}


def normalize_probes(data):
    """补全 healthcheck 探针的缺失字段。"""
    for hc_group in data.get("healthcheck", []):
        for p in hc_group.get("data", []):
            if not isinstance(p, dict):
                continue
            # 通用字段补全
            p.setdefault("initialDelaySeconds", 10)
            p.setdefault("periodSeconds", 5)
            p.setdefault("timeoutSeconds", 5)
            p.setdefault("successThreshold", 1)
            p.setdefault("failureThreshold", 3)
            if p.get("type") == "httpGet":
                p.setdefault("path", "/readyz" if p.get("name") == "readinessProbe" else "/livez")
            if p.get("type") == "command":
                p.setdefault("command", [])
    return data


def ensure_probe_diff(data):
    """确保 readinessProbe 和 livenessProbe 的属性不完全相同。"""
    for hc_group in data.get("healthcheck", []):
        probes = hc_group.get("data", [])
        readiness = None
        liveness = None
        for p in probes:
            if p.get("name") == "readinessProbe":
                readiness = p
            elif p.get("name") == "livenessProbe":
                liveness = p
        if readiness and liveness:
            # 至少在一个字段上做出区分
            if all(readiness.get(k) == liveness.get(k) for k in ["type", "port", "path", "initialDelaySeconds", "periodSeconds", "timeoutSeconds"]):
                liveness["initialDelaySeconds"] = (liveness.get("initialDelaySeconds", 10) or 10) + 5
    return data


def _ensure_resource_labels(resource_list, ctx, default_name_suffix):
    """确保 scope 不是 paas 的资源组（environments / secrets）都有必填 labels。"""
    module_group = ctx.get("repo_group", "").replace("-", "/")
    repo_group = ctx.get("repo_group", "")
    module_name = ctx.get("module_name", "")
    for res in resource_list:
        scope = res.get("scope", "all")
        if scope != "paas":
            if "labels" not in res or not isinstance(res.get("labels"), dict) or not res.get("labels"):
                res["labels"] = {}
            labels = res["labels"]
            name = repo_group + "-" + module_name + default_name_suffix
            labels.setdefault("app.kubernetes.io/code-repo", repo_group + "_" + module_name)
            labels.setdefault("app.kubernetes.io/name", name)
            labels.setdefault("app.kubernetes.io/part-of", module_group)


def ensure_labels(data, ctx):
    """确保 environments 和 secrets 的 labels 合规。"""
    _ensure_resource_labels(data.get("environments", []), ctx, "-common-config")
    _ensure_resource_labels(data.get("secrets", []), ctx, "-secret")
    return data


def _normalize_item(item, default_value=""):
    """补全单个 environments/secrets data 项的缺失字段。"""
    if not isinstance(item, dict):
        item = {}
    defaults = {
        "name": "",
        "type": "value",
        "value": default_value,
        "group": "default",
        "configurable": True,
        "option_values": [default_value] if default_value else [],
        "configure_name": "",
        "built_in_variable": False,
        "conditions": [],
        "switch_type": "",
        "required": True,
        "is_self_config": True,
        "b64encode": False,
        "is_config_file": False,
        "description": "TODO: 补充说明",
        "meaning": "TODO: 补充含义",
        "type": "value",
        "skip_inject": False,
        "valueFrom": {},
    }
    for key, val in defaults.items():
        if key not in item:
            item[key] = val
        elif key == "valueFrom" and item.get("type") == "valueFrom" and not item.get("valueFrom"):
            # type=valueFrom 时 valueFrom 不能是空对象，但这里先保留原有值
            pass
    return item


COMMON_ENV_DEFAULTS = {
    "SERVER_PORT": "8080",
    "GROUP_ID": "1010",
    "USER_ID": "1010",
    "DATA_DIR": "/data/volume",
    "TZ": "Asia/Shanghai",
    "SPRING_BOOT_STARTER": "tomcat",
}


def _infer_default_value(name, extracted_default=""):
    """根据变量名推断合理的默认值。"""
    if extracted_default:
        return extracted_default
    if name in COMMON_ENV_DEFAULTS:
        return COMMON_ENV_DEFAULTS[name]
    if name.endswith("PORT"):
        return "8080"
    if name.endswith("PATH"):
        return "/tmp"
    return ""


def normalize_config_items(data):
    """遍历 environments 和 secrets 的 data，补全缺失字段并推断默认值。同时补全环境级别和 switches 的缺失字段。"""
    for env in data.get("environments", []):
        env.setdefault("conditions", [])
        env.setdefault("switch_type", "")
        for it in _ensure_list(env.get("data")):
            default_val = _infer_default_value(it.get("name", ""), it.get("value", ""))
            it["value"] = default_val
        env["data"] = [_normalize_item(it, it.get("value", "")) for it in _ensure_list(env.get("data"))]
    for sec in data.get("secrets", []):
        sec.setdefault("type", "Opaque")
        sec.setdefault("conditions", [])
        sec.setdefault("switch_type", "")
        for it in _ensure_list(sec.get("data")):
            default_val = _infer_default_value(it.get("name", ""), it.get("value", ""))
            it["value"] = default_val
        sec["data"] = [_normalize_item(it, it.get("value", "")) for it in _ensure_list(sec.get("data"))]
    for sw in data.get("switches", []):
        sw.setdefault("is_self_config", True)
    # 补全 resources 缺失字段
    for res_group in data.get("resources", []):
        for res in _ensure_list(res_group.get("data")):
            if isinstance(res, dict):
                res.setdefault("ephemeral-storage", "5Gi")
    return data


def upgrade_from_legacy(root, data, ctx):
    """读取旧版 app.json 和 docker-compose.yml，提取配置填充到新版结构。"""
    old_app_path = os.path.join(root, "app.json")
    docker_compose_path = os.path.join(root, "docker-compose.yml")

    old_data = _load_json(old_app_path)
    if old_data:
        # 1. 提取旧版内联 healthcheck/volumes/resources/ports 到第一级
        old_apps = _ensure_list(old_data.get("applications"))
        if old_apps:
            old_containers = _ensure_list(old_apps[0].get("containers"))
            if old_containers:
                old_specs = _ensure_list(old_containers[0].get("spec"))
                if old_specs:
                    old_spec = _ensure_dict(old_specs[0])

                    # healthcheck
                    if "healthcheck" in old_spec and "healthcheck_ref" not in old_spec:
                        hc = old_spec["healthcheck"]
                        if isinstance(hc, list) and hc:
                            data["healthcheck"] = [{"name": "common-health-check", "data": hc}]

                    # volumes
                    if "volumes" in old_spec and "volumes_ref" not in old_spec:
                        vols = old_spec["volumes"]
                        if isinstance(vols, list) and vols:
                            data["volumes"] = [{"name": "common-volumes", "data": vols}]

                    # resources
                    if "resources" in old_spec and "resources_ref" not in old_spec:
                        res = old_spec["resources"]
                        if isinstance(res, list) and res:
                            data["resources"] = [{"name": "common-resources", "data": res}]

                    # runtime-interpreter 层级修正
                    if "runtime-interpreter" in old_data:
                        for app in data.get("applications", []):
                            for container in app.get("containers", []):
                                for spec in container.get("spec", []):
                                    spec["runtime-interpreter"] = _ensure_list(old_data.get("runtime-interpreter"))

        # 2. 提取旧版 environments / secrets / switches（若它们已在第一级）
        if "environments" in old_data:
            data["environments"] = old_data["environments"]
        if "secrets" in old_data:
            data["secrets"] = old_data["secrets"]
        if "switches" in old_data:
            data["switches"] = old_data["switches"]

    # 3. 从 docker-compose.yml 提取 environment
    if os.path.exists(docker_compose_path):
        content = _read_file(docker_compose_path)
        env_section = re.search(r'environment:\s*\n((?:\s+-?\s*\S+.*\n)+)', content)
        if env_section:
            env_data = []
            for line in env_section.group(1).split("\n"):
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                # 移除前导的 "- "
                if stripped.startswith("-"):
                    stripped = stripped[1:].strip()
                if "=" not in stripped:
                    continue
                key, val = stripped.split("=", 1)
                key = key.strip()
                val = val.strip()
                # 解析默认值
                configurable = False
                default_val = val
                m = re.match(r'\$\{(?P<var>[\w-]+):-(?P<def>[^}]+)\}', val)
                if m:
                    configurable = True
                    default_val = m.group("def")
                elif val.startswith("$"):
                    configurable = True
                    default_val = _infer_default_value(key, "")

                env_data.append({
                    "name": key,
                    "value": default_val,
                    "group": "default",
                    "configurable": configurable,
                    "option_values": [default_val] if default_val else [],
                    "configure_name": "",
                    "built_in_variable": False,
                    "conditions": [],
                    "required": True,
                    "is_self_config": True,
                    "b64encode": False,
                    "is_config_file": False,
                    "description": "TODO: 补充说明",
                    "meaning": "TODO: 补充含义",
                    "type": "value",
                    "skip_inject": False,
                })

            if env_data:
                # 合并到已有的 environments 中（保留 SERVER_PORT / GROUP_ID / USER_ID 避免重复）
                existing_env = _ensure_list(data.get("environments"))
                common_config_name = ctx.get("repo_group", "") + "-" + ctx.get("module_name", "") + "-common-config"
                target_env = None
                for env in existing_env:
                    if env.get("name") == common_config_name:
                        target_env = env
                        break
                if not target_env:
                    target_env = {
                        "name": common_config_name,
                        "labels": {
                            "app.kubernetes.io/code-repo": ctx.get("repo_group", "") + "_" + ctx.get("module_name", ""),
                            "app.kubernetes.io/name": common_config_name,
                            "app.kubernetes.io/part-of": ctx.get("repo_group", "").replace("-", "/"),
                        },
                        "scope": data.get("applications", [{}])[0].get("scope", "all") if data.get("applications") else "all",
                        "data": [],
                    }
                    existing_env.append(target_env)

                existing_keys = {item.get("name") for item in target_env.get("data", [])}
                for item in env_data:
                    if item["name"] not in existing_keys:
                        target_env.setdefault("data", []).append(item)
                        existing_keys.add(item["name"])
                data["environments"] = existing_env

    return data


def main():
    parser = argparse.ArgumentParser(description="Generate CI v3 app.json")
    parser.add_argument("--root", required=True, help="项目根目录")
    parser.add_argument("--module-name", required=True, help="模块名/仓库名")
    parser.add_argument("--repo-group", required=True, help="仓库组名")
    parser.add_argument("--server-port", type=int, default=8080, help="服务监听端口")
    parser.add_argument("--exposed-port", type=int, default=48080, help="对外暴露端口")
    parser.add_argument("--framework", default="unknown", help="技术栈: go/java/web/python/cpp")
    parser.add_argument("--orchestration-type", default="docker-compose-and-kubernetes",
                        help="部署方式: docker-compose / kubernetes / docker-compose-and-kubernetes / none")
    parser.add_argument("--upgrade", action="store_true", help="是否读取旧版配置并迁移")
    parser.add_argument("--output", default="", help="输出文件路径，默认 stdout")
    args = parser.parse_args()

    skill_dir = get_skill_dir()
    template_text = load_template(skill_dir)

    ctx = {
        "module_name": args.module_name,
        "repo_group": args.repo_group,
        "server_port": args.server_port,
        "exposed_port": args.exposed_port,
        "framework": args.framework,
        "orchestration_type": args.orchestration_type,
    }

    text = replace_placeholders(template_text, ctx)
    data = json.loads(text)

    data = adjust_for_framework(data, args.framework)
    data = adjust_scope(data, args.orchestration_type)
    data = normalize_probes(data)
    data = ensure_probe_diff(data)
    data = ensure_labels(data, ctx)

    if args.upgrade:
        data = upgrade_from_legacy(args.root, data, ctx)

    data = normalize_probes(data)
    data = normalize_config_items(data)

    result = json.dumps(data, indent=2, ensure_ascii=False)

    out_path = args.output or os.path.join(args.root, "app.json")
    if args.output == "-" or (not args.output and sys.stdout.isatty()):
        # Python 2 兼容：print unicode 到 pipe 可能报错
        if sys.version_info[0] < 3:
            sys.stdout.write(result.encode("utf-8"))
            sys.stdout.write(b"\n")
        else:
            print(result)
    else:
        _write_file(out_path, result)
        if sys.version_info[0] < 3:
            sys.stdout.write(("已生成: " + out_path).encode("utf-8"))
            sys.stdout.write(b"\n")
        else:
            print("已生成: " + out_path)


if __name__ == "__main__":
    main()

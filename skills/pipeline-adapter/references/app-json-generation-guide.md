# app.json 生成详细指南

**本文档目标**：确保生成的 `app.json` 100% 符合 CI v3 规范，字段层级、类型、必填项无一遗漏。

**使用方式**：
- **新项目**：直接运行 `python scripts/generate_app_json.py --root {项目根目录} --module-name {NAME} --repo-group {GROUP} ...`。
- **旧版升级**：运行脚本时附加 `--upgrade` 参数，脚本会自动读取旧版配置并按规范迁移。
- **手动修正**：若需要手动调整，必须对照本文档中“完整结构示例”和“字段映射速查表”逐条核对。

---

## 一、生成原则（强制）

1. **新项目禁止从零手写 JSON**。必须基于 `assets/templates/app.json` 模板复制并替换占位符。
2. **旧版升级禁止直接覆盖模板**。必须先读取旧文件、提取有效配置、按本文档的“旧版迁移映射”转换后填入模板。
3. **生成后必须校验**：运行 `python scripts/validate_app_json.py {项目根目录}/app.json`（如存在）。没有校验脚本时，必须手工对照本文档“检查清单”逐项勾选。

---

## 二、完整结构示例（单服务通用版）

```json
{
  "component_type": "application",
  "access_service_governance": false,
  "applications": [
    {
      "type": "deployment",
      "scope": "all",
      "containers": [
        {
          "type": "general",
          "spec": [
            {
              "name": "{REPO_GROUP}-{REPO_NAME}",
              "runtime-interpreter": [],
              "healthcheck_ref": { "name": "common-health-check" },
              "volumes_ref": { "name": "common-volumes" },
              "resources_ref": { "name": "common-resources" },
              "env": [],
              "envFrom": [
                { "type": "configMapRef", "name": "{REPO_GROUP}-{REPO_NAME}-common-config" }
              ],
              "service_name": "",
              "ports": [
                {
                  "name": "{SERVER_PORT}",
                  "protocol": "TCP",
                  "port": {EXPOSED_PORT},
                  "targetPort": {SERVER_PORT}
                }
              ],
              "scope": "all"
            }
          ]
        }
      ]
    }
  ],
  "switches": [
    {
      "name": "ingress-enable",
      "value": "True",
      "operator": "==",
      "origin_expression": "config[\"ingress-enable\"] == True",
      "is_built_in": true,
      "is_self_config": true,
      "meaning": "是否开启 Ingress 访问",
      "option_values": ["true", "false"]
    }
  ],
  "environments": [
    {
      "name": "{REPO_GROUP}-{REPO_NAME}-common-config",
      "labels": {
        "app.kubernetes.io/code-repo": "{REPO_GROUP}_{REPO_NAME}",
        "app.kubernetes.io/name": "{REPO_GROUP}-{REPO_NAME}-common-config",
        "app.kubernetes.io/part-of": "{MODULE_GROUP}"
      },
      "scope": "all",
      "data": [
        {
          "name": "GROUP_ID",
          "value": "1010",
          "group": "default",
          "configurable": true,
          "option_values": ["1010"],
          "configure_name": "",
          "built_in_variable": false,
          "conditions": [],
          "switch_type": "",
          "required": true,
          "is_self_config": true,
          "b64encode": false,
          "is_config_file": false,
          "description": "运行用户组编号",
          "meaning": "运行用户组编号",
          "type": "value",
          "skip_inject": false,
          "valueFrom": {}
        },
        {
          "name": "USER_ID",
          "value": "1010",
          "group": "default",
          "configurable": true,
          "option_values": ["1010"],
          "configure_name": "",
          "built_in_variable": false,
          "conditions": [],
          "switch_type": "",
          "required": true,
          "is_self_config": true,
          "b64encode": false,
          "is_config_file": false,
          "description": "运行用户编号",
          "meaning": "运行用户编号",
          "type": "value",
          "skip_inject": false,
          "valueFrom": {}
        },
        {
          "name": "SERVER_PORT",
          "value": "{SERVER_PORT}",
          "group": "default",
          "configurable": true,
          "option_values": ["{SERVER_PORT}"],
          "configure_name": "",
          "built_in_variable": false,
          "conditions": [],
          "switch_type": "",
          "required": true,
          "is_self_config": true,
          "b64encode": false,
          "is_config_file": false,
          "description": "服务监听端口",
          "meaning": "服务监听端口",
          "type": "value",
          "skip_inject": false,
          "valueFrom": {}
        }
      ]
    }
  ],
  "secrets": [
    {
      "name": "{REPO_GROUP}-{REPO_NAME}-secret",
      "labels": {
        "app.kubernetes.io/code-repo": "{REPO_GROUP}_{REPO_NAME}",
        "app.kubernetes.io/name": "{REPO_GROUP}-{REPO_NAME}-secret",
        "app.kubernetes.io/part-of": "{MODULE_GROUP}"
      },
      "scope": "all",
      "type": "Opaque",
      "data": [
        {
          "name": "EXAMPLE_PASSWORD",
          "value": "change-me",
          "group": "default",
          "configurable": true,
          "option_values": ["change-me"],
          "configure_name": "",
          "built_in_variable": false,
          "conditions": [],
          "switch_type": "",
          "required": true,
          "is_self_config": true,
          "b64encode": true,
          "is_config_file": false,
          "description": "示例密码",
          "meaning": "示例密码",
          "type": "value",
          "skip_inject": false,
          "valueFrom": {}
        }
      ]
    }
  ],
  "healthcheck": [
    {
      "name": "common-health-check",
      "data": [
        {
          "name": "readinessProbe",
          "type": "httpGet",
          "port": "${SERVER_PORT}",
          "initialDelaySeconds": 10,
          "periodSeconds": 5,
          "timeoutSeconds": 5,
          "successThreshold": 1,
          "failureThreshold": 3,
          "path": "/readyz"
        },
        {
          "name": "livenessProbe",
          "type": "httpGet",
          "port": "${SERVER_PORT}",
          "initialDelaySeconds": 15,
          "periodSeconds": 5,
          "timeoutSeconds": 5,
          "successThreshold": 1,
          "failureThreshold": 3,
          "path": "/livez"
        },
        {
          "name": "startupProbe",
          "type": "httpGet",
          "port": "${SERVER_PORT}",
          "path": "/readyz",
          "initialDelaySeconds": 10,
          "periodSeconds": 5,
          "timeoutSeconds": 5,
          "successThreshold": 1,
          "failureThreshold": 30
        }
      ]
    }
  ],
  "resources": [
    {
      "name": "common-resources",
      "data": [
        {
          "type": "limits",
          "cpu": "200m",
          "memory": "128Mi",
          "ephemeral-storage": "5Gi"
        },
        {
          "type": "requests",
          "cpu": "200m",
          "memory": "128Mi",
          "ephemeral-storage": "5Gi"
        }
      ]
    }
  ],
  "volumes": [
    {
      "name": "common-volumes",
      "data": [
        {
          "name": "data",
          "type": "bind",
          "source_from": "file",
          "src": "${DATA_DIR}/${APP_NAME}/var/log",
          "dst": "${MODULE_NAME_UPPER_HYPHEN_WORKING_DIR}/var/log",
          "size": "2Gi"
        }
      ]
    }
  ]
}
```

**关键说明**：
- `applications[].containers[].spec[].name` 必须使用 `{REPO_GROUP}-{REPO_NAME}` 格式。
- `healthcheck[].data[].port` 在 `app.json` 内是**字符串**，写 `"${SERVER_PORT}"`（不是 `{{SERVER_PORT}}`）。
- `volumes[].data[].dst` 是**运行时占位符**，写 `"$GO-DEMO_WORKING_DIR/var/log"`（不带花括号）。
- `ports[].port`（即 `EXPOSED_PORT`）和 `ports[].targetPort`（即 `SERVER_PORT`）是**整数**，不加引号。

---

## 三、按技术栈的 `runtime-interpreter` 配置

生成 `app.json` 后，必须根据技术栈在 `applications[].containers[].spec[].runtime-interpreter` 中补充对应条目：

| 技术栈 | 推荐 runtime-interpreter |
|--------|-------------------------|
| **Java** | `[{"name": "jdk", "version": "1.8", "type": "JavaRunTimeEnv"}]`（版本按实际，1.8/11/17） |
| **Web（nginx 前端）** | `[{"name": "nginx", "version": "1.23", "type": "ReverseProxy"}]` |
| **Web（tonghttpserver）** | `[{"name": "tonghttpserver", "version": "1.0", "type": "ReverseProxy"}]` |
| **Java（TongWeb）** | 追加 `[{"name": "tongweb", "version": "7.0", "type": "WebContainer"}]` |
| **Java（BES）** | 追加 `[{"name": "bes-appserver", "version": "9.5", "type": "WebContainer"}]` |
| **Python** | 如有需要：`[{"name": "python", "version": "3.8", "type": "PythonInterpreter"}]` |

**注意**：`runtime-interpreter` 是**数组**，每个元素必须包含 `name`、`version`、`type` 三个字段，`type` 只允许：`ReverseProxy`、`WebContainer`、`JavaRunTimeEnv`、`PythonInterpreter`。

---

## 四、旧版迁移映射速查表

### 4.1 `healthcheck` / `volumes` / `resources` / `ports` 迁移

旧版位置（错误） | 新版位置（正确）
---|---
`applications[].containers[].spec[].healthcheck` | 提升到 `healthcheck`（第一级数组），`spec` 中用 `"healthcheck_ref": {"name": "xxx"}` 引用
`applications[].containers[].spec[].volumes` | 提升到 `volumes`（第一级数组），`spec` 中用 `"volumes_ref": {"name": "xxx"}` 引用
`applications[].containers[].spec[].resources` | 提升到 `resources`（第一级数组），`spec` 中用 `"resources_ref": {"name": "xxx"}` 引用
`applications[].containers[].spec[].ports` | 保留在 `spec[].ports`（**这是唯一不需要 _ref 的**），但也可提升到第一级用 `ports_ref`
`app.json` 顶层 `runtime-interpreter` | 迁移到 `applications[].containers[].spec[].runtime-interpreter`

### 4.2 `environment` 迁移（docker-compose / K8S ConfigMap → app.json）

旧版来源 | 新版字段 | 规则
---|---|---
`docker-compose.yml` `environment:` 中 `KEY=$VALUE` | `environments[].data[].name` | 取 `KEY`（大写）
同上 | `value` | 若值为 `${VAR:-default}` 取 `default`；若为 `${VAR}`（无默认值），脚本会自动推断常见默认值（如 `GROUP_ID` → `1010`、`SERVER_PORT` → `8080`、`TZ` → `Asia/Shanghai` 等）；若为纯字符串直接复制
同上 | `configurable` | 原值含 `$` 变量占位符则 `true`，否则 `false`
K8S ConfigMap `data:` 中 `key: {{ env['xxx'] \| default('yyy') }}` | `configure_name` | 取 `xxx`
K8S ConfigMap `data:` 中 `key: {{ config["xxx"] \| default('yyy') }}` | `built_in_variable` | `true`

### 4.3 容器名称统一规则

对于已有 `docker-compose.yml` 的旧项目：
- **必须以 `docker-compose.yml` 中的 `services.<name>` 为准**
- 修改 `app.json` 的 `spec[].name` 与之保持一致
- 修改 K8S YAML 的 `containers[].name` 与之保持一致

**示例**：
```yaml
# docker-compose.yml
services:
  demo-go-demo:
    container_name: demo-go-demo
    hostname: demo-go-demo
```
```json
// app.json
{
  "applications": [{
    "containers": [{
      "spec": [{
        "name": "demo-go-demo"
      }]
    }]
  }]
}
```

---

## 五、字段必填与格式速查

### 5.1 `switches` 元素

字段 | 必填 | 类型 | 说明
---|---|---|---
`name` | **是** | string | 开关 key，如 `ingress-enable`
`value` | **是** | string | 默认值，如 `"True"`
`operator` | 否 | string | 一般为 `==` 或 `!=`
`origin_expression` | 否 | string | 原 Jinja2 条件表达式
`is_built_in` | 否 | bool | `config["xxx"]` 形式为 `true`
`is_self_config` | 否 | bool | 是否本模块声明，默认 `true`
`meaning` | **是** | string | **必须中文，不能为空**
`option_values` | 否 | array(string) | 建议布尔类写 `["true", "false"]`

### 5.2 `environments[].data` / `secrets[].data` 元素

**`secrets[].data` 与 `environments[].data` 结构完全一致**，每个元素必须包含完整的通用字段，缺失字段生成时必须补全为默认值。

#### `environments[]` / `secrets[]` 的 `labels` 要求
- **当 `scope` 不是 `paas` 时，`labels` 为必填属性，不能为空**。
- `environments` 必须包含以下 3 个 label：
  ```json
  {
    "app.kubernetes.io/code-repo": "{REPO_GROUP}_{REPO_NAME}",
    "app.kubernetes.io/name": "{REPO_GROUP}-{REPO_NAME}-common-config",
    "app.kubernetes.io/part-of": "{MODULE_GROUP}"
  }
  ```
- `secrets` 必须包含以下 3 个 label（`name` 后缀通常为 `-secret`）：
  ```json
  {
    "app.kubernetes.io/code-repo": "{REPO_GROUP}_{REPO_NAME}",
    "app.kubernetes.io/name": "{REPO_GROUP}-{REPO_NAME}-secret",
    "app.kubernetes.io/part-of": "{MODULE_GROUP}"
  }
  ```

#### 通用字段说明（environments.data / secrets.data）

字段 | 必填 | 类型 | 常用值
---|---|---|---
`name` | **是** | string | 大写+下划线，如 `SERVER_PORT`
`type` | **是** | string | `value` 或 `valueFrom`
`value` | 视情况 | string/number | 默认值；`type=valueFrom` 可不填
`group` | 否 | string | `default`
`configurable` | 否 | bool | `true`（变量）/ `false`（常量）
`option_values` | 否 | array | `[value]`
`configure_name` | 否 | string | 对应 `{{ env['xxx'] }}`；与 `name` 小写转中划线一致时可留空
`built_in_variable` | 否 | bool | `config["xxx"]` 时 `true`，否则 `false`
`conditions` | 否 | array | 基础项目 `[]`
`switch_type` | 否 | string | 如 `file_switch` / `key_value_switch`，默认 `""`
`required` | 否 | bool | `true`
`is_self_config` | 否 | bool | `true`
`b64encode` | 否 | bool | `false`
`is_config_file` | 否 | bool | `false`
`description` | **是** | string | **不能为空**
`meaning` | **是** | string | **不能为空**
`skip_inject` | 否 | bool | `false`
`valueFrom` | 否 | object | `type=valueFrom` 时填写，如 `secretKeyRef`

### 5.3 `healthcheck[].data` 元素

字段 | 必填 | 说明
---|---|---
`name` | 是 | `readinessProbe`、`livenessProbe` 或 `startupProbe`
`type` | 是 | `httpGet` / `tcpSocket` / `command`
`port` | 视情况 | HTTP/TCP 服务填端口字符串，如 `"${SERVER_PORT}"`
`path` | 视情况 | `type=httpGet` 时必填，如 `/readyz`
`command` | 视情况 | `type=command` 时必填数组
`initialDelaySeconds` | 否 | 默认 `10`
`periodSeconds` | 否 | 默认 `5`
`timeoutSeconds` | 否 | 默认 `5`
`successThreshold` | 否 | 成功阈值，默认 `1`
`failureThreshold` | 否 | 失败阈值，默认 `3`；`startupProbe` 可适当放大

**重要**：`readinessProbe`、`livenessProbe`、`startupProbe` 不能完全相同，至少要区分为 `initialDelaySeconds` 或 `timeoutSeconds`。

### 5.4 `resources[].data` 元素

每个资源组必须恰好包含两条：一条 `type=limits`，一条 `type=requests`。

```json
{
  "type": "limits",
  "cpu": "200m",
  "memory": "128Mi",
  "ephemeral-storage": "",
  "memory_configure_name": "",
  "cpu_configure_name": "",
  "ephemeral_storage_configure_name": ""
}
```

### 5.5 `volumes[].data` 元素

字段 | 必填 | 说明
---|---|---
`name` | 是 | 卷名，如 `logs`
`type` | 是 | `bind` / `emptyDir` / `configMap` / `secret` / `PVC` / `VCT`
`source_from` | 是 | `bind`→`file`/`dir`；`emptyDir`→`dir`；`configMap`→名称；`secret`→名称；`PVC/VCT`→StorageClass
`src` | 视情况 | 宿主机路径 / 字段名 / PVC名称 / VCT留空
`dst` | 是 | **必须以 `$XXX_WORKING_DIR` 占位符开头**，如 `$GO-DEMO_WORKING_DIR/var/log`
`size` | 否 | 持久卷时声明，如 `"2Gi"`

**禁止**：Secret 禁止用 `configMap` 类型挂载，必须用 `"type": "secret"`。

---

## 六、检查清单（生成后必须核对）

在把 `app.json` 写入磁盘之前，逐条确认：

- [ ] `component_type` 为 `"application"`（普通服务）或 `"infra"`（中间件）
- [ ] `applications[].containers[].spec[].name` 格式正确：`{REPO_GROUP}-{REPO_NAME}`
- [ ] `runtime-interpreter` 层级正确，且包含 `{name, version, type}` 数组
- [ ] `healthcheck` / `volumes` / `resources` 位于第一级，且 `spec` 中使用 `_ref` 引用
- [ ] `environments` / `secrets` / `switches` 位于第一级
- [ ] `switches[].name`、`switches[].value`、`switches[].meaning` 均非空，`is_self_config` 已补全
- [ ] `environments.data[].meaning` 和 `description` 均非空，`switch_type`、`valueFrom` 已补全
- [ ] **当 `environments[].scope` 和 `secrets[].scope` 不是 `paas` 时，`labels` 必填且包含 3 个标准 label**
- [ ] `healthcheck[].data[].readinessProbe`、`livenessProbe`、`startupProbe`（如有）不完全相同，且包含 `successThreshold`、`failureThreshold`
- [ ] K8S YAML 中的 `readinessProbe` 与 `livenessProbe` **必须保留完整配置，不能清空为仅标签名**（Job 除外），且属性与 `app.json` 的 `healthcheck` 完全一致
- [ ] `ports[].port` 为整数，`ports[].targetPort` 为整数
- [ ] `envFrom` 中引用 secrets 时使用 `"secretRef"`（不是 `configMapRef`）
- [ ] `volumes[].data[].dst` 使用正确的工作目录占位符格式（`$GO-DEMO_WORKING_DIR/...`，不带花括号）
- [ ] JSON 语法有效（无尾随逗号、字符串引号匹配、整数不加引号）

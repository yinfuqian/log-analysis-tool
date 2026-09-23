# app.json 规范速查（新版）

## 作用
在 CI v3「编译与部署分离」模式下，`app.json` 是运行时镜像的**唯一配置数据源**。平台在部署阶段读取该文件，自动生成运行时镜像及编排文件（docker-compose、K8S YAML、ConfigMap、Secret 等）。

## 结构概览
```json
{
  "component_type": "application",
  "access_service_governance": false,
  "applications": [...],
  "switches": [...],
  "environments": [...],
  "secrets": [...],
  "healthcheck": [...],
  "resources": [...],
  "volumes": [...],
  "ports": [...]
}
```

### `component_type` 取值
- `"application"`：普通应用服务（默认）。
- `"infra"`：基础设施/中间件（如 MySQL、Redis、Etcd 等），流水线会按中间件规范处理镜像和编排。

## 关键字段

### applications / containers / spec
- `name`: 容器名称，一般为模块名。
- `scope`: 生效范围。可选值 `all`（docker + k8s）、`paas`（仅 docker-compose）、`kubernetes`（仅 K8S）。
- `runtime-interpreter`（可选）：声明运行时解释器/中间件数组，由流水线在构建运行时镜像时**自动注入**到目标路径，**无需**在 Dockerfile 中手动 COPY。
  ```json
  "runtime-interpreter": [
    { "name": "jdk", "version": "1.8", "type": "JavaRunTimeEnv" }
  ]
  ```
  - `type` 取值：`ReverseProxy`、`WebContainer`、`JavaRunTimeEnv`、`PythonInterpreter`。
  - **Java 项目**：必须声明，如 `"jdk"`（版本如 `"1.8"`、`"11"`、`"17"` 等），`type` 填 `JavaRunTimeEnv`。流水线会将对应版本的 JDK 注入到容器内 `${APP_DIR}/share/jdk`（`APP_DIR` 默认为 `/app`，平台可覆盖）。
    - 国产化 Web 容器：`{ "name": "tongweb", "version": "7.0", "type": "WebContainer" }`、`{ "name": "bes-appserver", "version": "9.5", "type": "WebContainer" }`。
  - **Web 项目**：可声明反向代理或 Web 容器，如 `{ "name": "nginx", "version": "1.23", "type": "ReverseProxy" }`。
    - 国产化反向代理：`{ "name": "tonghttpserver", "version": "1.0", "type": "ReverseProxy" }`。
  - **Python/Node 项目**：如需要特定版本解释器，也可通过该字段声明，`type` 对应 `PythonInterpreter` / `WebContainer` 等，由流水线自动注入到容器内 `${APP_DIR}/share/` 下（`APP_DIR` 默认为 `/app`，平台可覆盖）。
  - **定制化发行版（国产化 JDK / Python）**：若需替换为指定发行版本（如国产化定制 JDK），必须声明对应 `type`（`JavaRunTimeEnv` 或 `PythonInterpreter`）。
  - **License 处理**：涉及国产化中间件（TongWeb、TongHttpServer、BES 等）时：
    - **Docker 版本**：将 license 文件挂载到持久化目录（如 `/data/volumes/reverse-proxy-license`）。
    - **K8S 版本**：将 license 内容更新到 `configmap` 中 `license` 的 `DATA` 字段内。
- `healthcheck_ref`: 引用 `healthcheck` 中定义的探针组。
- `volumes_ref`: 引用 `volumes` 中定义的卷组。
- `resources_ref`: 引用 `resources` 中定义的资源组。
- `ports_ref`: 引用 `ports` 中定义的端口组（可选，volumes 同理）。
- `env`: 仅声明当前容器**特有**的环境变量（数组）。
- `envFrom`: 引用 `environments` 或 `secrets` 的 name（数组）。
  - 引用 `environments` 时，`type` 为 `"configMapRef"`（对应 K8S ConfigMap）。
  - 引用 `secrets` 时，`type` 为 `"secretRef"`（对应 K8S Secret）。
  - **禁止**将 `secrets` 用 `configMapRef` 引用。
- `service_name`: `scope=kubernetes` 时对应 deployment 的 container name；`scope=paas` 时对应 docker-compose 的 service name。

### healthcheck
提升到 `app.json` 第一级，通过 `healthcheck_ref` 在 spec 中引用。
- `readinessProbe`：就绪探针。`type` 可为 `httpGet` / `tcpSocket` / `command`。
- `livenessProbe`：存活探针。`type` 同上。
- `startupProbe`：启动探针（中间件/启动慢的服务推荐使用），`type` 同上。启动探针成功后才会启用 readiness/liveness。
- 三者属性不能完全相同。
- 典型字段：`name`, `type`, `port`, `path`, `initialDelaySeconds`, `periodSeconds`, `timeoutSeconds`, `successThreshold`, `failureThreshold`, `command`。
  - `successThreshold`：探测成功阈值，默认 `1`。
  - `failureThreshold`：探测失败阈值，默认 `3`；`startupProbe` 可适当放大（如 `30`）。

### resources
提升到 `app.json` 第一级，通过 `resources_ref` 在 spec 中引用。
必须同时包含 `limits` 和 `requests`：
```json
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
```
- `ephemeral-storage`：临时存储限制（如 `"30Gi"`），K8S 调度与容器运行时磁盘限制使用。
- `ephemeral_storage_configure_name`：对应一键部署工具中的临时存储变量名。

### volumes
提升到 `app.json` 第一级，通过 `volumes_ref` 在 spec 中引用。
- `type`: `"bind"`、`"emptyDir"`、`"configMap"`、`"secret"`、`"PVC"`、`"VCT"`
- `source_from`:
  - `bind` 类型：`"file"` 或 `"dir"`
  - `emptyDir` 类型：`"dir"`
  - `configMap` 类型：ConfigMap 名称
  - `secret` 类型：Secret 名称
  - `PVC` / `VCT` 类型：StorageClass 名称
- `src`: 宿主机路径、ConfigMap/Secret 中的字段名、PVC 名称，或空字符串
- `dst`: 容器内目标路径，可用占位符 `$MODULE_WORKING_DIR`
- `size`: 持久卷时声明大小，如 `"2Gi"`

**重要**：`secret` 类型在 K8S 中生成时会使用 `secret: secretName: ...`，**禁止**用 `configMap` 形式挂载 Secret。

### runtime-dep-resources（可选）
大模型相关仓库可在 `spec` 中声明 `runtime-dep-resources`，避免每次构建都将大体积模型文件拷贝到二进制镜像中。流水线会在构建运行时镜像时自动拉取指定镜像并挂载到目标路径。

```json
"runtime-dep-resources": [
  {
    "name": "go-admin/model-pkg-image",
    "version": "v1.0.2",
    "src": "/app",
    "dst": "${APP_DIR}/resources/models"
  }
]
```

### ports
提升到 `app.json` 第一级，可直接在 spec 的 `ports` 中内联，也可使用 `ports_ref` 引用。
```json
{
  "name": "http",
  "protocol": "TCP",
  "port": 48080,
  "targetPort": 8080
}
```

## 配置统一声明（environments / secrets）

### environments
每个 `environment` 类似于一个 ConfigMap 声明，它的 `data` 是一组配置项的声明列表。声明的 `environment` 可在 `spec` 中通过 `envFrom` 引用。

#### environment 字段
- `name`: 该环境配置组的唯一名称，一般格式为 `{repo-group}-{repo-name}-common-config`。
- `labels`: 保留与原 configmap 相同的 labels，保证向下兼容。
  - **当 `scope` 不是 `paas` 时，`labels` 为必填属性，不能为空**。
  - 必须包含以下 label（保证 K8S 自动生成 ConfigMap 时标签正确）：
    ```json
    {
      "app.kubernetes.io/code-repo": "{REPO_GROUP}_{REPO_NAME}",
      "app.kubernetes.io/name": "{REPO_GROUP}-{REPO_NAME}-common-config",
      "app.kubernetes.io/part-of": "{MODULE_GROUP}"
    }
    ```
- `scope`: 声明该配置适用的编排范围。可选值 `all`、`paas`、`kubernetes`。
- `conditions`: 条件判断数组。若该环境组需要被 `{% if %}` 包裹则填写，基础项目默认 `[]`。
- `switch_type`: 开关类型。如 `file_switch`（整组配置是否生效）、`key_value_switch`（单个 key-value 是否生效），基础项目默认 `""`。
- `data`: 配置项数组，字段见下表。

### secrets
与 `environments` 类似，但类比于 k8s 的 Secret，值会被 base64 编码存储。
- `type`: 如 `"Opaque"`。
- `labels`: **当 `scope` 不是 `paas` 时，`labels` 为必填属性，不能为空**。
  - 必须包含以下 label：
    ```json
    {
      "app.kubernetes.io/code-repo": "{REPO_GROUP}_{REPO_NAME}",
      "app.kubernetes.io/name": "{REPO_GROUP}-{REPO_NAME}-secret",
      "app.kubernetes.io/part-of": "{MODULE_GROUP}"
    }
    ```
- `data`: **与 `environments[].data` 结构完全一致**，必须包含完整的配置项通用字段（见下表），生成时缺失的字段必须补全为默认值。密码类建议 `b64encode: true`。

### 配置项通用字段（environments.data / secrets.data / spec.env）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 注入到容器中的配置项 key，大写下划线组合 |
| `type` | string | 是 | `value`（普通值）或 `valueFrom`（引用） |
| `value` | any | 否 | 默认值。`type=valueFrom` 时可不填 |
| `group` | string | 否 | 分组名，默认 `default` |
| `configurable` | bool | 否 | 是否对外可配置。默认 `true` |
| `option_values` | array | 否 | 可选值枚举列表 |
| `configure_name` | string | 否 | 对应编排模板中 `{{ env['xxx'] }}` 的 `xxx`。若与 `name` 的小写+下划线转中划线一致，可留空，流水线会自动按该规则转换 |
| `built_in_variable` | bool | 否 | 是否为一键部署工具内置变量（仅 `config["xxx"]` 形式为 `true`） |
| `conditions` | array | 否 | 条件判断。若原 yaml 被 `{% if %}` 包裹则必填 |
| `required` | bool | 否 | 是否必填，默认 `true` |
| `is_self_config` | bool | 否 | 是否本模块声明。引用其他模块时填 `false` |
| `b64encode` | bool | 否 | 是否 base64 编码，密码类可填 `true` |
| `is_config_file` | bool | 否 | 是否为配置文件（大文本），默认 `false` |
| `description` | string | **是** | 配置项详细说明，**不能为空** |
| `meaning` | string | **是** | 配置项简短含义，**不能为空** |
| `skip_inject` | bool | 否 | 是否跳过注入容器，默认 `false` |
| `valueFrom` | object | 否 | `type=valueFrom` 时填写，如 `fieldRef`、`secretKeyRef`、`configMapKeyRef` |

## switches 字段
用于声明 K8S YAML 中 Jinja2 模版的开关变量。

### 必填字段（不能为空）

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | **是** | 开关的 key，对应模板中使用的变量名（如 `ingress-enable`）。 |
| `value` | **是** | 该开关的默认值。 |
| `meaning` | **是** | **必须补充中文含义**，为空时流水线编译报错。 |

### 字段示例
```json
{
  "name": "ingress-enable",
  "value": "True",
  "operator": "==",
  "origin_expression": "config[\"ingress-enable\"] == True",
  "is_built_in": true,
  "is_self_config": true,
  "meaning": "是否开启 Ingress",
  "option_values": ["true", "false"]
}
```
- `is_built_in`: `config["xxx"]` 开头为 `true`，`env["xxx"]` 开头为 `false`。
- `is_self_config`: 是否本模块声明，默认 `true`。
- `option_values`: 开关的可选值列表，建议布尔类填写 `["true", "false"]`。

## 占位符

### 模板占位符（生成阶段替换）

| 占位符 | 替换结果示例 | 说明 |
|--------|-------------|------|
| `{{MODULE_NAME}}` | `go-demo` | 原始模块名 |
| `{{MODULE_GROUP}}` | `demo` | 仓库组名 |
| `{{REPO_NAME}}` | `go-demo` | 同 MODULE_NAME |
| `{{REPO_GROUP}}` | `demo` | 同 MODULE_GROUP，斜杠换中划线 |
| `{{MODULE_NAME_UPPER}}` | `GO_DEMO` | 大写+下划线（用于环境变量名） |
| `{{MODULE_NAME_UPPER_HYPHEN}}` | `GO-DEMO` | 大写但保留中划线 |
| `{{MODULE_NAME_UPPER_HYPHEN_WORKING_DIR}}` | `$GO-DEMO_WORKING_DIR` | 工作目录占位符，**不能带花括号** |
| `{{MODULE_NAME_UPPER_HYPHEN_IMAGE_TAG}}` | `$GO-DEMO_IMAGE_TAG` | 镜像标签占位符 |
| `{{SERVER_PORT}}` | `8080` | 服务监听端口 |
| `{{EXPOSED_PORT}}` | `48080` | Service 对外暴露端口 |

### 运行时占位符（部署阶段替换）
- `{{MODULE_NAME_UPPER_HYPHEN_WORKING_DIR}}` → 如 `$GO-DEMO_WORKING_DIR`，容器内工作目录（**不能**写成 `${GO-DEMO_WORKING_DIR}`）
- `{{MODULE_NAME_UPPER_HYPHEN_IMAGE_TAG}}` → 如 `$GO-DEMO_IMAGE_TAG`，镜像标签变量

## 兼容性说明
- 新版不再在 `spec` 中直接内联声明 `healthcheck`、`volumes`、`resources`，必须提升到第一级并使用 `_ref` 引用。
- 新版不再手工维护 `deployments/kubernetes/*_config-map.yaml`，所有环境变量统一收敛到 `app.json` 的 `environments` 中，由流水线自动生成 configmap。

# 旧版流水线升级适配详细指南

本文档描述如何将已接入旧版流水线的项目升级为 CI v3 新版格式。
**只在项目存在旧版特征时读取本文件。**

## 判断是否为旧版接入项目

若项目已存在以下任一旧版特征，则视为**升级场景**：
1. `app.json` 中直接使用内联 `healthcheck` / `volumes` / `resources` / `ports`（无 `_ref`引用）。
2. `docker-compose.yml` 的 `environment:` 下填充了实际配置项。
3. `deployments/kubernetes/*_config-map.yaml` 存在且包含非空 `data`。
4. K8S `deployment.yaml` 的 `env` / `envFrom` / `resources` 下填充了实际内容。

## 升级适配步骤（严禁直接覆盖模板）

### (1) 读取旧版 `app.json`
提取已有信息（`component_type`、`applications`、端口等），用于构建新版 `app.json`。

### (2) 修正字段层级错位
若旧版 `app.json` 中存在字段放置层级错误，生成新版时必须**修正到正确位置**。常见错位包括：
- `runtime-interpreter`：**必须**放在 `applications[].containers[].spec[]` 下，**禁止**放在 `app.json` 顶层或其他位置。
- `healthcheck` / `volumes` / `resources` / `ports`：**必须**提升到 `app.json` 第一级，并通过 `_ref` 在 `spec` 中引用；禁止直接内联在 `spec` 中。
- `environments` / `secrets` / `switches`：**必须**放在 `app.json` 第一级，禁止放在 `applications` 或 `spec` 内部。

**处理规则**：
1. 扫描旧版 `app.json` 全文，发现错位字段时迁移到规范位置。
2. 迁移后删除原错误位置的字段，避免重复。
3. 若字段内容不完整，按规范补全默认值或生成 TODO 提醒。

### (3) 读取 docker-compose 中的环境变量
**必须遍历** `docker-compose.yml` 中 `services.*.environment` 列表，把形如 `KEY=$VALUE` 或 `KEY=${VALUE:-default}` 的条目提取并转换为 `app.json` 的 `environments.data` 配置项。

**字段映射规则**：
- `name`: 环境变量名（大写）
- `value`: 默认值（去掉 `$` 和花括号后的 default）
- `configurable`: 若原值使用了变量占位符则为 `true`；纯常量则为 `false`
- `group`: `default`
- `meaning`/`description`: 若原注释中有中文说明则提取填入，否则空字符串（TODO 提醒补充）
- `type`: `value`
- `built_in_variable`: `false`
- `is_self_config`: `true`
- `b64encode`: `false`
- `is_config_file`: `false`
- `skip_inject`: `false`
- `conditions`: `[]`
- `required`: `true`
- `option_values`: `[value]`

### (4) 读取 K8S ConfigMap
如果存在 `deployments/kubernetes/*_config-map.yaml`，**必须遍历**其 `data:` 字段，把每个 key-value 提取并转换为 `app.json` 的 `environments.data` 配置项。

- 若 value 是 `{{ env['xxx'] | default('yyy') }}` 形式：
  - `configurable` = `true`
  - `configure_name` = `xxx`（编排模板中 `env['xxx']` 的 `xxx` 必须与此对应；若与 `name` 的小写+中划线形式一致，可留空）
  - `value` = `yyy`
- 若 value 是 `{{ config["xxx"] | default('yyy') }}` 形式：
  - `built_in_variable` = `true`
  - `configurable` = `true`
- 若 key 对应密码（如包含 `password`、`secret`、`token`），`b64encode` 视原模板决定（默认 `false`）。

### (5) 合并 environment 作用域
- docker-compose 和 K8S ConfigMap **共用的配置项**（key 相同），合并为一个 `environment`，`scope` = `all`，`name` = `{REPO_GROUP}-{REPO_NAME}-common-config`。
- 仅 docker-compose 使用的配置项，`scope` = `paas`。
- 仅 K8S 使用的配置项，`scope` = `kubernetes`。

### (6) 容器名称一致性检查与统一
**检查范围**：
- `docker-compose.yml` 中的 `services.<name>`（服务名）
- `docker-compose.yml` 中的 `container_name`
- `docker-compose.yml` 中的 `hostname`
- `app.json` 中的 `applications[].containers[].spec[].name`
- K8S YAML 中的 `containers[].name`

**处理规则**：
1. **已接入过流水线且存在 `docker-compose.yml` 的旧项目**：
   - **必须以 `docker-compose.yml` 中的 `services.<name>` 为准**
   - 统一修改 `app.json` 中的 `spec[].name` 与该服务名保持一致
   - 统一修改 K8S YAML 中的 `containers[].name` 与该服务名保持一致
   - 统一修改 `docker-compose.yml` 中的 `container_name` 和 `hostname` 与服务名保持一致
   - 即使 docker-compose 中的服务名看起来不够规范，也要以它为准，保证升级后原有 docker-compose 部署不被破坏。

2. **不存在 `docker-compose.yml` 的旧项目**（仅 K8S）：
   - 以 K8S YAML 中现有 `containers[].name` 为准，同步修改 `app.json` 中的 `spec[].name`
   - 若 K8S 中的名称也不规范，则统一修正为 `{REPO_GROUP}-{REPO_NAME}`

### (7) 清理旧版部署文件
- **docker-compose.yml**：
  - **删除 `environment:` 标签下所有配置项**，但保留 `environment:` 标签本身（**仅留空标签，不要加 `[]`**）
  - **删除 `resources:` 标签下所有子项**，但保留 `resources:` 标签本身（**仅留空标签，不要加 `[]`**）
  - **volumes 需要保留**：目前挂载卷**尚未实现**从 `app.json` 自动替换到编排文件，因此 `docker-compose.yml` 中的 `volumes` 配置**必须保留**并手动维护
- **K8S deployment yaml**：
  - 删除 `env:` / `envFrom:` / `resources:` 下的所有子项，但保留空标签本身（**不要加 `[]`**）
  - **`readinessProbe` 和 `livenessProbe` 不能清空**：必须保留完整配置，且属性要与 `app.json` 的 `healthcheck` 保持一致（Job 除外）
  - **volumes 需要保留**：目前挂载卷**尚未实现**从 `app.json` 自动替换到编排文件，因此 K8S YAML 中的 `volumes` 和 `volumeMounts` 配置**必须保留**并手动维护
- **K8S config-map yaml**：**直接删除** `deployments/kubernetes/*_config-map.yaml`（新版由流水线自动生成）。

**重要：volumes 一致性要求**
虽然挂载卷配置需要同时在 `app.json` 和编排文件中维护，但**必须确保两者一致**：
- `app.json` 中的 `volumes[].data[].src` 和编排文件中的宿主机路径必须一致
- `app.json` 中的 `volumes[].data[].dst` 和编排文件中的容器内路径必须一致

### (8) 读取 switches
若旧版 K8S YAML（尤其是 Ingress）中存在 `{% if config["xxx"] == True %}` 或 `{% if env["xxx"] == "yyy" %}` 的 Jinja2 条件语句，提取并生成 `switches` 数组。

### (9) 兜底补全基础环境变量
无论旧版文件是否声明了环境变量，升级后必须确保 `app.json` 的 `environments` 中包含：
- **`SERVER_PORT`**：服务监听端口，默认值从识别到的服务端口号获取（默认 8080）
  - `configurable`: `true`
  - `scope`: 根据编排形式决定（`all` / `kubernetes` / `paas`）
  - `group`: `default`
  - `description` / `meaning`: "服务监听端口"
  - `required`: `true`
  - `is_self_config`: `true`

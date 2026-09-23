# Pipeline Adapter 分步详细指南

本文档是 `SKILL.md` 中 Step 1-8 的详细展开版。执行接入流程时，先阅读 `SKILL.md` 了解全貌，再按步骤进入本文档查看具体操作细节。

---

## Step 1: 识别项目信息

### 自动探测（优先使用脚本）
**必须首先运行**：
```bash
python3 scripts/detect_project_info.py {项目根目录}
```

脚本会返回：
- `framework`: `go` / `java` / `web` / `python` / `cpp` / `unknown`
- `module_name`: 仓库名
- `repo_group`: 仓库组（可能为 `null`，若无法推断需询问用户）
- `legacy`: 是否存在旧版文件及旧版特征

### REPO_GROUP 获取检查
若 `repo_group` 为 `null`，**必须询问用户**：
```
⚠️ 无法自动推断 REPO_GROUP（仓库所属组），请提供（如：demo、bot、call、learn）：
```

### 新项目信息确认（必须交互）
若 `legacy.is_legacy_project == false`，**禁止直接生成文件**。逐个确认：

1. **基本信息**（一次性告知已推断值，请用户确认或修正）：
   ```
   该项目为新接入项目，已推断出以下基本信息：
   - 模块名：{MODULE_NAME}
   - 仓库组：{REPO_GROUP}
   - 技术栈：{framework}
   - 服务端口：{SERVER_PORT}（默认 8080）
   请确认或修正：
   ```
2. **部署方式**（选项）：
   ```
   请选择部署方式（默认 C）：
   A. 仅 docker-compose
   B. 仅 K8S
   C. 同时支持 docker-compose + K8S
   ```
3. **Ingress 需求**（若含 K8S）：
   ```
   是否需要 Ingress 外部访问？
   A. 是
   B. 否（默认）
   ```
4. **外部依赖 / hook.sh 初始化**（若含 docker-compose）：
   ```
   是否有数据库/外部服务依赖，需要通过 hook.sh 初始化？
   A. 是
   B. 否（默认）
   ```
5. **特殊说明**（兜底）：
   ```
   是否有其他特殊说明？（如非 HTTP 服务、需要 StatefulSet 等）
   没有请直接回复「无」。
   ```

**多架构规则**：
- `java`、`web` 等架构无关技术栈：**禁止询问**多架构，直接配置：
  ```yaml
  platform: ["arch-independent"]
  builderPlatform: "linux/amd64"
  ```
- `python` 默认视为可能涉及架构相关原生库，如需确认是否纯 Python（无 C 扩展），可询问；确认后同样配置 `arch-independent`。
- `go`、`cpp` 默认按多架构处理。

---

## Step 2: 旧版升级检测与自动适配

### 判断依据
若 `detect_project_info.py` 返回 `legacy.is_legacy_project == true`，视为升级场景。
常见旧版特征：
- `app.json` 内联 `healthcheck` / `volumes` / `resources` / `ports`
- `docker-compose.yml` 的 `environment:` 下填充了实际配置项
- 存在 `deployments/kubernetes/*_config-map.yaml`
- K8S `deployment.yaml` 的 `env` / `envFrom:` / `resources:` 下填充了实际内容

### 升级必读
**遇到旧版项目时，严禁直接覆盖模板！**
**立即读取 `references/upgrade-workflow.md` 并按文档步骤执行迁移。**

升级核心要点（速查）：
1. 修正 `runtime-interpreter` 层级到 `applications[].containers[].spec[]`。
2. `healthcheck` / `volumes` / `resources` / `ports` 提升到 `app.json` 第一级，用 `_ref` 引用。
3. 提取 `docker-compose.yml` 的 `environment` 到 `app.json` 的 `environments.data`。
4. 提取 K8S ConfigMap 到 `app.json` 的 `environments.data`。
5. **容器名称一致性**：已接入过且存在 `docker-compose.yml` 的，**必须以 `services.<name>` 为准**，同步修改 `app.json` 和 K8S YAML。
6. 清理旧版文件：
   - docker-compose.yml：清空 `environment:` 内容但保留空标签；清空 `resources:` 内容但保留空标签（**不要加 `[]`**）。`volumes` 暂时保留。
   - K8S deployment：清空 `env:` / `envFrom:` / `resources:` 内容但保留空标签（**不要加 `[]`**）。`volumes` / `volumeMounts` 暂时保留。
   - 删除 `deployments/kubernetes/*_config-map.yaml`。

---

## Step 3: 复制新版模板（新接入项目）

### 默认环境变量
新版 `app.json` 模板已预置：
- `GROUP_ID` / `USER_ID` = `1010`
- `SERVER_PORT` = `8080`

### 模板路径映射

| 模板路径 | 项目目标路径 | 适用 `orchestration.type` |
|---------|-------------|--------------------------|
| `ci.yaml` | `{项目根目录}/ci.yaml` | 所有 |
| `Dockerfile` | `{项目根目录}/Dockerfile`（单模块）<br>`{项目根目录}/Dockerfile.{模块名}`（多模块） | 所有 |
| `app.json` | `{项目根目录}/app.json`（**必须使用 `generate_app_json.py` 生成**） | 所有 |
| `build.sh` | `{项目根目录}/build_files/build.sh` | 所有 |
| `apprt` | `{项目根目录}/deployments/binary/apprt` | 所有 |
| `sonar-project.properties` | `{项目根目录}/sonar-project.properties` | 所有 |
| `docker-compose.yml` | `{项目根目录}/docker-compose.yml` | `docker-compose` / `docker-compose-and-kubernetes` |
| `dependence_install.sh` | `{项目根目录}/deployments/binary/dependence_install.sh` | `docker-compose` / `docker-compose-and-kubernetes` |
| `k8s-deployment.yaml` | `{项目根目录}/deployments/kubernetes/{REPO_GROUP}_{REPO_NAME}_deployment.yaml` | `kubernetes` / `docker-compose-and-kubernetes` |
| `k8s-service.yaml` | `{项目根目录}/deployments/kubernetes/{REPO_GROUP}_{REPO_NAME}_service.yaml` | `kubernetes` / `docker-compose-and-kubernetes` |
| `k8s-ingress.yaml` | `{项目根目录}/deployments/kubernetes/{REPO_GROUP}_{REPO_NAME}_ingress.yaml` | `kubernetes` / `docker-compose-and-kubernetes` |
| `k8s-statefulset.yaml` | 按需生成 | `kubernetes` / `docker-compose-and-kubernetes` |
| `k8s-job.yaml` | 按需生成 | `kubernetes` / `docker-compose-and-kubernetes` |
| `hook.sh` | `{项目根目录}/hook.sh` | `docker-compose` / `docker-compose-and-kubernetes` |

### 占位符替换规则
- `{{MODULE_NAME}}` → 模块名
- `{{MODULE_GROUP}}` / `{{REPO_NAME}}` / `{{REPO_GROUP}}` → 仓库组/名（`REPO_GROUP` 中 `/` 替换为 `-`）
- `{{MODULE_NAME_UPPER}}` → 大写+下划线（如 `GO_DEMO`）
- `{{MODULE_NAME_UPPER_HYPHEN}}` → 大写保留中划线（如 `GO-DEMO`）
- `{{MODULE_NAME_UPPER_HYPHEN_WORKING_DIR}}` → `$GO-DEMO_WORKING_DIR`（**模块名中的连字符必须保留，严禁替换为下划线**）
- `{{MODULE_NAME_UPPER_HYPHEN_IMAGE_TAG}}` → `$GO-DEMO_IMAGE_TAG`（**模块名中的连字符必须保留，严禁替换为下划线**）
- `{{SERVER_PORT}}` → 服务端口
- `{{EXPOSED_PORT}}` → 对外端口（默认 `48080`）

### ci.yaml `modules` 字段规则
- **单服务**：`modules` 为空字符串 `""`（默认）。
- **多模块**：`modules` 用逗号分隔子模块名，如 `"moduleA,moduleB"`。
  - Dockerfile 命名：`Dockerfile.moduleA`、`Dockerfile.moduleB`
  - 编排文件和 `app.json` 必须包含每个子模块的独立配置。

---

## Step 4: 根据源码调整编译与启动命令

### Dockerfile 编译阶段
**编译方式可完全按项目定制**：直接用 `go build`、`mvn package`、`make build`、`npm run build` 或调用 `build_files/build.sh`。**不要直接复制模板 `build.sh` 调用而不做修改。**

硬约束只有两条：
1. 最后一个 `FROM` 必须是 `scratch`。
2. 编译产物必须按规范复制到 `${APP_DIR}/*` 目录（`APP_DIR` 默认为 `/app`，平台可通过 `--build-arg` 覆盖），且必须包含 `COPY ... app.json ${APP_DIR}/app.json`。

**技术栈专属模板**：
- `framework: web` → 从 `assets/templates/web/` 获取 Dockerfile、build.sh、apprt、sonar-project.properties
- `framework: python` → 从 `assets/templates/python/` 获取（如不存在则先创建）

### 详细技术栈检查点
生成文件后，**必须读取 `references/tech-stack-patterns.md` 并按文档逐项核对**：
- Go 项目是否启用了 `CGO_ENABLED=0` 和静态编译
- Java 项目是否正确声明了 `runtime-interpreter`（`type: JavaRunTimeEnv`），`apprt` 中是否通过 `WORKDIR` 推导 JDK 路径（禁止硬编码 `/app/share/jdk`）
- Web 项目的 `nginx.conf` 变量是否与 `app.json` 的 `name` 对应
- Python 项目的解释器路径是否一致
- 国产化中间件（TongWeb / BES / TongHttpServer）是否在 `apprt` 中增加了 `transform.sh` 调用

---

## Step 5: app.json 生成规范（禁止手写）

### 强制要求
**无论新项目还是旧版升级，`app.json` 必须优先通过脚本生成，禁止让模型从零手写 JSON。**

**新项目命令示例**：
```bash
python3 scripts/generate_app_json.py \
  --root {项目根目录} \
  --module-name {MODULE_NAME} \
  --repo-group {REPO_GROUP} \
  --server-port {SERVER_PORT} \
  --exposed-port {EXPOSED_PORT} \
  --framework {go|java|web|python|cpp} \
  --orchestration-type {docker-compose|kubernetes|docker-compose-and-kubernetes|none}
```

**旧版升级命令示例**（追加 `--upgrade`）：
```bash
python3 scripts/generate_app_json.py \
  --root {项目根目录} \
  --module-name {MODULE_NAME} \
  --repo-group {REPO_GROUP} \
  ... \
  --upgrade
```

脚本功能：
1. 自动加载 `assets/templates/app.json` 模板并替换占位符
2. 自动根据技术栈填充 `runtime-interpreter`
3. 自动根据部署方式调整 `scope`
4. 自动确保 `readinessProbe` 与 `livenessProbe` 属性不完全相同
5. 旧版升级时自动迁移 `docker-compose.yml` 的 `environment` 和旧 `app.json` 的内联配置

生成后若需手动微调，**必须对照 `references/app-json-generation-guide.md` 逐项核对**。

### 必填且不能为空字段
以下字段若为空会导致流水线报错，生成时必须确保有值：
- `switches[].name`
- `switches[].value`
- `switches[].meaning`
- `environments.data[].meaning`
- `environments.data[].description`

### 层级规范（常见错误）
- `runtime-interpreter`：**必须**在 `applications[].containers[].spec[]` 下
- `healthcheck` / `volumes` / `resources`：**必须**在 `app.json` 第一级，通过 `_ref` 在 `spec` 中引用
- `environments` / `secrets` / `switches`：**必须**在 `app.json` 第一级

### `envFrom` 引用规范
```json
// 正确
"envFrom": [
  { "type": "configMapRef", "name": "demo-go-demo-common-config" },
  { "type": "secretRef",    "name": "database-credentials" }
]

// 错误：secrets 不能用 configMapRef
"envFrom": [
  { "type": "configMapRef", "name": "database-credentials" }  // ← 错误！
]
```

### volumes 类型规范
| 类型 | `type` 值 | `source_from` | 说明 |
|------|----------|---------------|------|
| 主机路径-文件 | `bind` | `file` | 宿主机文件路径 |
| 主机路径-目录 | `bind` | `dir` | 宿主机目录路径 |
| 临时目录 | `emptyDir` | `dir` | 固定值 |
| ConfigMap | `configMap` | ConfigMap 名称 | - |
| **Secret** | **`secret`** | Secret 名称 | K8S 生成时用 `secret: secretName: ...` |
| PVC | `PVC` | StorageClass | - |
| VCT | `VCT` | StorageClass | - |

### `configure_name` 与模板变量对应关系
编排模板中的 `{{ env['xxx'] | default('yyy') }}`，其 `xxx` 对应 `app.json` 中该配置项的 `configure_name`；若 `configure_name` 为空，则取 `name` 的小写并将下划线转为中划线。

例如 `name` 为 `TEST_STR` 时：
- `configure_name` 可留空（自动推导为 `test-str`）
- 模板中写 `{{ env['test-str'] | default('xxx') }}`

### runtime-interpreter 格式
```json
"runtime-interpreter": [
  { "name": "jdk", "version": "1.8", "type": "JavaRunTimeEnv" },
  { "name": "nginx", "version": "1.23", "type": "ReverseProxy" }
]
```
`type` 可选值：`ReverseProxy`、`WebContainer`、`JavaRunTimeEnv`、`PythonInterpreter`。

---

## Step 6: 规范校验与一致性检查

### 生成前自检清单（再次确认）
在告知用户"已完成"之前，逐项核对：

#### 1. 端口一致性
- `app.json`: `applications[].ports[].targetPort` = `{{SERVER_PORT}}`
- `app.json`: `healthcheck[].data[].port` 与 SERVER_PORT 一致
- K8S YAML 中所有端口引用使用 `{{ env['xxx'] | default(yyy) }}` 且默认值与 `app.json` 一致

#### 2. 编译输出与启动路径一致性
- `Dockerfile` 最后一个 `FROM` 为 `scratch`
- `Dockerfile` 包含 `COPY ... app.json /app/app.json`
- 制品存放路径与 `apprt` 执行路径一致（详见 `references/tech-stack-patterns.md`）

#### 3. 挂载卷一致性（手动维护）
- `app.json` 中每个卷在 `docker-compose.yml` 和 K8S YAML 中都有对应配置
- `src` 和 `dst` 完全一致
- `dst` 使用 `{{MODULE_NAME_UPPER_HYPHEN_WORKING_DIR}}` 占位符开头

#### 4. 容器名称一致性
- docker-compose `services.<name>` / `container_name` / `hostname` 保持一致
- `app.json` `spec[].name` 与上述名称一致
- K8S YAML `containers[].name` 与上述名称一致
- **旧项目**：以 `docker-compose.yml` 的 `services.<name>` 为准

#### 5. K8S Label Selector 严格一致（致命错误）
- **Deployment / StatefulSet 的 `selector.matchLabels` 必须与 `template.metadata.labels` 完全一致**（键和值都要相同）
- 特别检查 `app.kubernetes.io/name` 的值是否完全一致（不能一处用中划线、另一处用下划线）
- Service 的 `selector` 也必须与 Pod 模板中的 `app.kubernetes.io/name` 保持一致

#### 6. docker-compose 格式规范（强制校验）
生成 docker-compose.yml 后，**必须运行校验脚本**：
```bash
python3 scripts/validate_docker_compose.py {项目根目录}/docker-compose.yml
```

**规范要求**：
- 字符串值使用双引号
- 环境变量使用带默认值形式 `${VAR:-default}`（`$REGISTRY_ADDR`、`$XXX_WORKING_DIR`、`$XXX_IMAGE_TAG` **严禁**加默认值；特别注意 `$XXX_IMAGE_TAG` **禁止**写成 `${XXX_IMAGE_TAG:-latest}`）
- K8S YAML 与 docker-compose 中的 `image` 占位符均使用 `{{MODULE_NAME_UPPER_HYPHEN_IMAGE_TAG}}`，生成结果如 `$WEB-DEMO_IMAGE_TAG`（大写保留中划线，不带花括号）

**常见错误修正示例**：
```yaml
# 错误
ports:
  - $SERVER_PORT:$SERVER_PORT
# 正确
ports:
  - "${SERVER_PORT:-8080}:${SERVER_PORT:-8080}"

# 错误
volumes:
  - ${DATA_DIR}/logs:$GO-DEMO_WORKING_DIR/logs
# 正确
volumes:
  - "${DATA_DIR:-/data/volume}/logs:$GO-DEMO_WORKING_DIR/logs"
```

#### 7. 健康检查端点（K8S YAML 探针不能清空）
**必须运行**：
```bash
python3 scripts/scan_health_endpoints.py {项目根目录}
```
- 若 `framework` 为 `web`，`app.json` 中 `readinessProbe` 默认用 `tcpSocket`（仅检测端口），`livenessProbe` 用 `httpGet` `/`，两者不能完全相同
- 若源码中存在 `/readyz` 和 `/livez` → 直接配置（`web` 项目除外）
- 若源码中存在其他端点（如 `/health`、`/hello`）→ **仍按规范配置 `/readyz` 和 `/livez`**（`web` 项目除外），并生成 TODO 提醒用户补充实现
- 若源码中未实现任何端点 → 仍按规范配置 `/readyz` 和 `/livez`（`web` 项目除外），并生成 TODO
- `readinessProbe` 与 `livenessProbe` 属性不能完全相同
- **K8S YAML 中的 `readinessProbe` 和 `livenessProbe` 必须保留完整配置，不能清空为仅标签名**（与 `env:` / `resources:` 不同）；其属性必须与 `app.json` 的 `healthcheck` 完全一致
  - 特别注意：`web` 项目的 K8S YAML 中 `readinessProbe` 用 `tcpSocket`（删除 `path`），`livenessProbe` 用 `httpGet` `/`，与 `app.json` 保持一致

#### 8. Secret 挂载规范
- `envFrom` 引用 secrets 时用 `"secretRef"`
- K8S YAML `volumes` 中 Secret 使用 `secret: secretName: ...`，禁止用 `configMap`

#### 9. 空标签规范（注意探针不清空）
- K8S deployment yaml：`env:` / `envFrom:` / `resources:` 仅留空标签，**不要加 `[]`**
- K8S deployment yaml：`readinessProbe` / `livenessProbe` **必须保留完整配置，不能清空**（Job 除外），且属性与 `app.json` 的 `healthcheck` 对齐
- docker-compose.yml：`environment:` / `resources:` 仅留空标签，**不要加 `[]`**

#### 10. K8S YAML Jinja2 占位符引号规范
- **字符串值**：外层必须用双引号，内部 `env['xxx']` 用单引号，如 `"{{ env['server-port'] | default(8080) }}"`
- **严禁**外层和内层都用单引号，如 `'{{ env['server-port'] | default(8080) }}'`（YAML 解析会出错）
- **整数值**（如 `port`、`targetPort`、`number`、`nodePort`）：**不要加外层引号**，保持为 int 类型

### 按需读取的 references
| 检查项 | 参考文件 |
|--------|---------|
| `ci.yaml` 规范 | `references/ci-v3-spec.md` |
| `app.json` 完整字段说明 | `references/app-json-spec.md` |
| `app.json` 生成详细指南（含完整示例和检查清单） | `references/app-json-generation-guide.md` |
| K8S YAML 规范 | `references/k8s-yaml-spec.md` |
| docker-compose 规范 | `references/paas-spec.md` |
| sonar 配置规范 | `references/sonar-spec.md` |
| 旧版升级步骤 | `references/upgrade-workflow.md` |
| 各技术栈模式 | `references/tech-stack-patterns.md` |

---

## Step 7: 列出 TODO 并提醒用户

遍历所有生成的文件，提取包含 `TODO` 注释的行，汇总输出：
```
以下是仍需你确认或补充的 TODO 项：
- Dockerfile:3   # TODO: 改这里为产品/组件名
- app.json:25    # TODO: 根据模块具体情况调整健康检查路径
...
```

**特别提醒**：
- `app.json` 中所有 `meaning` 和 `description`
- `app.json` 中所有 `switches[].meaning`
- Dockerfile 编译阶段具体步骤
- 未实现 `/readyz` / `/livez` 的项目需要补充端点

---

## Step 8: 验证建议

```bash
# 验证 Dockerfile 能否构建
docker build --build-arg COMMIT=$(git rev-parse --short HEAD) .
```

> docker-compose.yml 和 K8S YAML 中包含流水线占位符，需在平台编译后替换，建议提交后由流水线自动验证。

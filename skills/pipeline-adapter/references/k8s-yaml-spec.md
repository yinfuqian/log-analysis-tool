# K8S 编排文件规范速查（新版）

## 验证工具
- 编排文件生成后，流水线会使用 **KubeScope** 进行规范检查。常见不通过原因包括：
  1. `readinessProbe` 与 `livenessProbe` 属性完全相同；
  2. `app.kubernetes.io/name` 标签缺失或与 `selector` 不一致；
  3. 端口默认值使用了字符串 `'8080'` 而不是整数 `8080`；
  4. 变量缺少 `default` 默认值。

## 目录与命名
- 所有编排文件必须放在 `{项目根目录}/deployments/kubernetes/` 下。
- 文件后缀必须是 `.yaml`（不能用 `.yml`）。
- 命名规范：`{Repo_Group}_{Repo_Name}_{Res_Type}.yaml`
  - `Repo_Group` 中的 `/` 替换为 `-`。
  - `Res_Type` 与 `kind` 对应（大驼峰转小写+中划线）。

| kind | 文件名示例 |
|------|-----------|
| Deployment | `demo_go-demo_deployment.yaml` |
| Service | `demo_go-demo_service.yaml` |
| Ingress | `demo_go-demo_ingress.yaml` |
| StatefulSet | `demo_go-demo_stateful-set.yaml` |
| Job | `demo_go-demo_job.yaml` |

## 强制要求
以下资源类型中，**Deployment / StatefulSet / Job 至少有一个**：
- 无状态服务 → `Deployment`
- 有状态服务 → `StatefulSet`
- 一次性任务（如冒烟测试）→ `Job`

所有服务必须有的文件：
- `*_deployment.yaml`（或 StatefulSet / Job）
- `*_service.yaml`
- `*_ingress.yaml`（按需）

**注意**：新版不再手工维护 `*_config-map.yaml` 和 `*_secret.yaml`。配置统一收敛到 `app.json` 中，由流水线编译时自动生成。

## 变更说明（旧版 -> 新版）
1. **Deployment / StatefulSet** 中的 `env:`、`envFrom:`、`resources:` 标签必须**保留但清空内容**（**仅留空标签，不要加 `[]`**）。流水线会在编译时根据 `app.json` 自动填充。
   - **特别注意**：`readinessProbe` 和 `livenessProbe`**不能清空**，必须保留完整配置（Job 除外），且属性值必须与 `app.json` 的 `healthcheck` 保持一致。
2. **不再生成 ConfigMap YAML**。以前 `data:` 中的环境变量全部迁移到 `app.json` 的 `environments` 中声明。
3. **标签规范**：
   必须包含以下标签（`app.kubernetes.io/code-repo` 与 `app.code_repo` 过渡期均可使用，但务必保证一致）：
   ```yaml
   app.kubernetes.io/code-repo: demo_go-demo
   app.kubernetes.io/name: demo_go-demo
   app.kubernetes.io/component: application
   app.kubernetes.io/part-of: demo
   ```

## 模板变量（Jinja2）
所有变量必须有 `default`：
- 字符串：`{{ env['xxx'] | default('test') }}`
- 整数（端口、资源）：`{{ env['xxx'] | default(8080) }}`

**`env['xxx']` 的 `xxx` 来源**：对应 `app.json` 中该配置项的 `configure_name`；若 `configure_name` 为空，则取 `name` 的小写并将下划线转为中划线（例如 `name` 为 `TEST_STR` 时，模板写 `{{ env['test-str'] }}`）。

## 强制字段
### Deployment / StatefulSet
- `resources` 标签必须存在（内容为空，由流水线填充）。
- `readinessProbe` 和 `livenessProbe`（Job 除外）。
  - 两者属性不能完全相同。
  - 常用 `httpGet`，HTTP 服务规范路径为 `/readyz`（就绪探针）和 `/livez`（存活探针）；**Web 前端项目默认 `readinessProbe` 用 `tcpSocket`（仅检测端口），`livenessProbe` 用 `httpGet` `/`，两者不能完全相同**；非 HTTP 服务可使用 `exec` 或 `tcpSocket`。
- `env` / `envFrom` 标签必须存在（内容为空，由流水线填充）。
- `imagePullSecrets`: `- name: registry-secrets`
- **volumes**：若挂载 Secret，必须使用 `secret` 类型：
  ```yaml
  volumes:
    - name: db-creds
      secret:
        secretName: database-credentials
  ```
  **禁止**将 Secret 用 `configMap` 形式挂载。

### Service
- `type`: `ClusterIP`（默认）或 `NodePort`
- `ports[].port`、`targetPort` 必须存在
- `selector.app.kubernetes.io/name` 必须与 Deployment label 一致

### Ingress（可选）
- 外层包裹条件判断：`{% if config["ingress-enable"] == True %}`
- `host` 中可用 `config["namespace-hash"]` 和 `config["ingress-domain-suffix"]`
- `backend.service.name` 必须指向对应 Service 的 `metadata.name`

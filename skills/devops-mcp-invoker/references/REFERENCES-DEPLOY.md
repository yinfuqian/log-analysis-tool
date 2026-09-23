# DevOps MCP Invoker - References: 升级应用终态日志处理

> **必读说明（Read First）**
>
> 本文件是 `SKILL.md` 的**执行级细节补充**，对应 [SKILL.md 工作流二：查看容器/Pod 日志](../SKILL.md#工作流二查看容器pod-日志) 和 [工作流三：升级环境应用](../SKILL.md#工作流三升级环境应用)。
> **在判断失败阶段、获取模块/冒烟日志、决定是否自修复前，必须先按本文件执行。**
>
> [← 返回 SKILL.md](../SKILL.md)

---

## 5. 升级应用终态日志处理细节

### 5.1 失败阶段判断

- **部署/更新阶段失败**：构建、打包、镜像推送、滚动更新、容器启动报错，应用未 Running。
- **冒烟阶段失败**：部署已成功，但冒烟测试、健康检查、接口验证报错。

### 5.2 日志获取

- 向 MCP 查询升级历史获取 `task_id`。
- 向 MCP 查询该任务的 Jenkins 日志链接，按 [REFERENCES-BUILD.md §4.2](./REFERENCES-BUILD.md#42-获取-jenkins-日志) 规则抓取（优先 `/consoleText`；context-mode 可用时优先使用；否则按当前客户端使用 PowerShell/Bash/Python/Node fallback）。
- 部署阶段失败 → 获取模块日志，不获取冒烟日志。
- 冒烟阶段失败 → 获取模块日志 + 冒烟日志。
- 无法判断 → 先获取模块日志；若 `run_smoke_test=true`，再获取冒烟日志。

### 5.3 模块日志

- `platform_type=paas`：查询对应 `service_name` 的 docker 容器日志。
- `platform_type=kubernetes`：查询对应 pod 的 kubernetes 日志。
- 默认取最近 1000 行或 MCP 支持的最大行数。

### 5.4 冒烟日志

- 仅 kubernetes 环境。
- 确认 `run_smoke_test=true`。
- 查询 pod 名包含 `env-verify` 的 kubernetes pod 日志，不传入 `label_selector`。

### 5.5 代码问题判断

**属于代码问题：**

- 编译错误、单元测试失败、配置解析失败、依赖缺失。
- 启动报错（panic、runtime error、bean creation error 等）。
- 冒烟失败根因是代码未暴露接口、返回错误或无健康检查端点。

**不属于代码问题（禁止自我修复）：**

- k8s 节点不足、docker daemon 异常、网络分区。
- RBAC 拒绝、镜像仓库无权限。
- 环境变量/secret 缺失、外部依赖不可达。
- Jenkinsfile 语法错误、stage 配置错误。

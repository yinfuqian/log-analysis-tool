# DevOps MCP Invoker - References: 编译失败处理与 CI 轮询

> **必读说明（Read First）**
>
> 本文件是 `SKILL.md` 的**执行级细节补充**，对应 [SKILL.md 工作流一：查询 CI 编译状态](../SKILL.md#工作流一查询-ci-编译状态）。
> **在查询 CI 编译状态以及编译失败触发自修复前，必须先按本文件执行。**
>
> [← 返回 SKILL.md](../SKILL.md)

---

## 4. 编译失败处理与 CI 轮询 {#4-编译失败处理与-ci-轮询}

### 4.1 轮询规则（running/created 状态） {#45-轮询规则}

`running`/`created` 是**中间状态，不是终态**。模型必须自动轮询到终态（`success` / 失败）或达到上限，**禁止**在此时向用户提供"稍后再次查询"等停止选项。

#### 轮询流程

1. 首次调用 `query_build_status`（`max_wait_seconds=10`）获取状态。
2. 若状态为 `running`/`created`：
   - 向用户展示当前状态、Jenkins 日志链接、已轮询次数/已等待时间。
   - **立即按当前客户端安排下一次查询，不要等待用户回复**：
     - **Claude Code**：调用 `ScheduleWakeup`，`delaySeconds=60`；`prompt` 必须包含目标仓库 `<code_repo>`、版本 `<version>`、当前已轮询次数 N、已等待时间，例如：
       "继续查询 `<code_repo>` `<version>` 的 CI 编译状态，当前已轮询 1 次/已等待 60 秒，最长 15 分钟/15 次"
     - **Codex**：使用当前 shell 等待 60 秒后继续查询；Windows PowerShell 用 `Start-Sleep -Seconds 60`，Bash 用 `sleep 60`。如果命令返回会持续运行的会话 ID，继续等待该会话结束，不要改问用户。
     - 若当前客户端提供原生后台任务/定时器，优先使用客户端能力。
3. 每次轮询继续后重新调用 `query_build_status`，并累计轮询次数。
4. 轮询上限（满足任一条件即停止）：
   - 累计达到 **15 次**，或
   - 累计达到 **15 分钟**。
   - 达到上限后仍为 `running`/`created` → 停止轮询，告知用户编译仍在运行但已超时，提供 Jenkins 日志链接。

#### 轮询期间约束

- `running`/`created` 期间**不获取 Jenkins 日志详细内容**。
- 展示 Jenkins 日志链接时，仅作为跳转入口，不展开内容。
- `success` 或失败状态 → 进入对应终态处理，不再轮询。

### 4.2 获取 Jenkins 日志 {#42-获取-jenkins-日志}

1. 从 MCP 返回中提取 Jenkins 日志链接。
2. **优先获取纯文本日志**：将链接末尾的 `/console` 或 `display/redirect` 替换为 `/consoleText`，减少 HTML 解析噪音。
3. **判断 context-mode 是否可用（可选能力，仅部分客户端安装）**：
   - 若 `mcp__plugin_context-mode_*` 工具未注册、不存在或调用报错 → 视为 context-mode 未安装，直接跳到第 5 步的 shell/Python/Node fallback。
   - 若可用 → 按第 4 步优先级抓取日志。
4. **按以下优先级抓取日志**（优先让日志字节留在沙箱/索引中，不进入主上下文）：
   - **首选 `ctx_fetch_and_index`**：调用 `mcp__plugin_context-mode_context-mode__ctx_fetch_and_index` 拉取 `/consoleText`，再用 `mcp__plugin_context-mode_context-mode__ctx_search` 提取关键错误片段。
   - **次选 `ctx_execute`**：若 `ctx_fetch_and_index` 不可用或被拦截，调用 `mcp__plugin_context-mode_context-mode__ctx_execute` 在沙箱内完成 fetch + grep，只把摘要输出到上下文。
5. **shell/Python/Node fallback**（context-mode 未安装或被拦截时使用，按当前客户端 shell 选择）：

   **Windows PowerShell（Windows 默认优先）**：
   ```powershell
   $content = (Invoke-WebRequest -Uri '<consoleText-url>' -UseBasicParsing).Content
   $content -split "`n" | Select-String -Pattern 'ERROR|FAILED|Exception|Traceback'
   ```

   **Linux/macOS Bash**：
   ```bash
   curl -fsSL '<consoleText-url>' | grep -E 'ERROR|FAILED|Exception|Traceback'
   ```

   **Python**：
   ```bash
   python -c "import urllib.request; print(urllib.request.urlopen('<consoleText-url>').read().decode('utf-8'))"
   ```

   **Node.js**：
   ```bash
   node -e "fetch('<consoleText-url>').then(r => r.text()).then(console.log)"
   ```
6. 过滤/提取关键错误片段（如 `ERROR`、`FAILED`、`Exception`、`Traceback`），避免大段日志进入上下文。

> **避免空转**：一旦确定 context-mode 不可用或 HTTP 工具被拦截，直接选择上述某一条 fallback 命令执行，不要反复发起无意义的空命令、`Bash(:)` 或空工具调用探测。

### 4.3 可自动修复 vs 不可自动修复

**可自动修复：**

- 代码编译错误（语法、类型、缺少导入）。
- 单元测试失败（断言、测试数据过期）。
- 简单配置错误（路径、值错误）。
- 依赖版本冲突或缺失。

**不可自动修复：**

- 平台/流水线配置错误（Jenkinsfile、agent）。
- 外部依赖服务不可达（DB、缓存、第三方 API）。
- 权限/网络/基础设施问题。
- 日志中无法定位具体代码位置或修复方案。

### 4.4 自我修复前提

1. 失败原因为"最近修改的代码导致且可自动修复"。
2. 当前工作目录在正确的业务仓库。
3. git 配置可用。
4. 修复尝试次数 < 3。

### 4.5 提交信息规范

提交信息必须满足项目 hook 脚本的校验规则：

```
[<type>] <简短描述>

--<story|task|bug|jira>=<value> --user=<git config user.name> <原commit第三行的其余信息>
- <修复点1>
- <修复点2>
```

- **类型标记**：标题第一行以 `[类型]` 开头，类型必须在项目白名单中（修复场景常用 `[fix]` / `[bugfix]`，具体以项目配置为准）。
- **标题长度**：标题长度（含类型标记）必须 ≥ 11 个字符。
- **关联单号**：必须包含 `--story=`、`--task=`、`--bug=` 或 `--jira=` 中的至少一个。
  - TAPD：`--story=1234567`、`--task=1234567`、`--bug=1234567`
  - JIRA：`--jira=SEE-99` 或 `--jira=https://jira.in.wezhuiyi.com/browse/SEE-99`
- **用户标记**：必须包含 `--user=<git config user.name>`。
- **提交者邮箱**：需符合项目邮箱域名要求（以项目 hook 的 `VALID_EMAIL_DOMAINS` 为准）。
- **Revert 提交**：以 `Revert` 开头的提交跳过规范检查。
- **第二行为空行**：标题与正文之间留一空行。
- **第三行**：沿用最近一次用户提交的 `--story=` / `--task=` / `--bug=` / `--jira=` 信息，并追加 `--user=<git config user.name>`。

示例（假设 `git config user.name` 为 `walkernie`）：
  ```
  [fix] 修复 app.json 中 readinessProbe 末尾多余逗号导致的 JSON 解析错误

  --story=1022383 --user=walkernie 【CI流程一期】代码提交规范检查 https://www.tapd.cn/51449271/s/1436535
  - 删除 app.json:22 的尾随逗号
  - 本地 JSON 校验通过
  ```

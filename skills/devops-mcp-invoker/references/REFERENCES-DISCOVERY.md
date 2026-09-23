# DevOps MCP Invoker - References: 工具发现

> **必读说明（Read First）**
>
> 本文件是 `SKILL.md` 的**执行级细节补充**，对应 [SKILL.md 工具发现](../SKILL.md#工具发现)。
> **在执行任何业务操作前，必须先按本文件流程确认目标 tool 存在且可访问。**
>
> [← 返回 SKILL.md](../SKILL.md)

---

## 2. 工具发现

### 2.1 工具命名与发现流程

MCP 工具名称由当前客户端决定，不要硬编码前缀：

- **Claude Code**：通常以 `mcp__pipeline-integration-mcp__<tool-name>` 格式自动暴露。
- **Codex**：使用 Codex 注入的 MCP 命名空间；server 名中的 `-` 可能规范化为 `_`，例如显示为 `mcp__pipeline_integration_mcp` 命名空间。实际名称以当前会话暴露的 tool 列表为准。
- 本文后续提到的 `query_build_status`、`get_environment_info`、`enable_hotreload` 等均为**语义 tool 名**，调用时按当前客户端的实际前缀组合。

发现流程：

1. **Claude Code**：尝试调用 `mcp__pipeline-integration-mcp__tools_list` 获取可用 tools。
   - 调用成功 → 获取工具列表，匹配语义对应的 tool。
   - 调用失败（`tool not found` / `method not found`）→ 当前客户端不支持 `tools_list`，直接尝试调用语义对应的业务 tool 进行探测。
2. **Codex**：直接使用当前会话已注入的 MCP tools，不要假设存在 `tools_list`，也不要为了获取工具列表直连 MCP endpoint。
3. 探测业务 tool 时：
   - 工具返回结果（无论成功或业务错误）→ tool 存在，继续流程。
   - `tool not found` → tool 不存在，停止并说明。
   - `session not found` / 连接错误 → 会话可能已失效：Claude Code 执行 `/clear` 或退出重进；Codex 重启或新建会话。
   - 401/403 → 假连接，按 [REFERENCES-CONNECTION.md §1.4](./REFERENCES-CONNECTION.md#14-刷新会话与假连接处理) 重新注册。
4. 可用 `claude mcp list`（Claude Code）或 `codex mcp list`（Codex）检查 MCP 服务器连接状态，但不要用它获取工具列表。
5. 禁止用 `curl`/`wget`/`python`/PowerShell 等任何方式直接访问 MCP endpoint 探测 tools。

### 2.2 输出原则

- 不展示完整 schema。
- 关键 tool 不存在时停止并说明。
- 实际调用时根据可用 tool 语义匹配，不硬编码 tool 名。

### 2.3 context-mode 工具可用性检查

对于需要抓取 Jenkins 日志/外部网页的场景（如编译失败处理、升级终态日志处理）：

1. 若当前客户端安装了 context-mode，优先检查 `mcp__plugin_context-mode_context-mode__ctx_fetch_and_index` 和 `mcp__plugin_context-mode_context-mode__ctx_execute` 是否可调用。
2. **若 context-mode 未安装或不可用**：
   - 直接跳过 context-mode 层级。
   - 后续日志抓取使用当前客户端的 shell/Python/Node fallback。
   - 不要尝试调用任何 `mcp__plugin_context-mode_*` 工具，避免报错空转。
3. **若 context-mode 可用**：后续日志抓取优先走 context-mode，保持日志字节不进入主上下文；不可用或调用失败时按第 2 条降级。

日志抓取 fallback（按当前 shell 选择，禁止用于 MCP endpoint）：

- **Windows PowerShell**：

  ```powershell
  $content = (Invoke-WebRequest -Uri '<consoleText-url>' -UseBasicParsing).Content
  $content -split "`n" | Select-String -Pattern 'ERROR|FAILED|Exception|Traceback'
  ```

- **Linux/macOS Bash**：

  ```bash
  curl -fsSL '<consoleText-url>' | grep -E 'ERROR|FAILED|Exception|Traceback'
  ```

- **Python**：

  ```bash
  python -c "import urllib.request; print(urllib.request.urlopen('<consoleText-url>').read().decode('utf-8'))"
  ```

- **Node.js**：

  ```bash
  node -e "fetch('<consoleText-url>').then(r => r.text()).then(console.log)"
  ```

> **避免空转**：不要通过反复发起无意义的 `Bash(:)`、空命令或空工具调用来确认能力。确定 context-mode 不可用后，直接选择当前 shell 的一条 fallback 命令执行。

---

## 3. 适配 MCP 新增功能

- 用户请求超出预定义工作流时，先工具发现，再语义匹配。
- 找到匹配 tool → 说明能力可用，收集参数，调用前让用户确认关键参数。
- 找不到匹配 tool → 说明未提供该能力，列出可用 tools。
- 新字段/参数以 schema 为准，用户未提供时不编造默认值。
- 旧版存在但当前已移除的 tool，按“找不到”处理。

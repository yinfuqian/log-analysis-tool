# DevOps MCP Invoker - References: MCP 连接与注册

> **必读说明（Read First）**
>
> 本文件是 `SKILL.md` 的**执行级细节补充**，对应 [SKILL.md 前置条件](../SKILL.md#前置条件)。
> **在调用任何 MCP business tool 前，必须先确认 MCP server 已正确注册且连接正常。**
>
> [← 返回 SKILL.md](../SKILL.md)

---

## 1. MCP 连接与注册细节

### 1.1 Streamable HTTP 调用流程

`pipeline-integration-mcp` 通过 **Streamable HTTP** 协议通信：

1. 客户端向服务端 `POST /mcp`，发送 `initialize` 请求建立会话。
2. 服务端返回初始化响应，响应头中可能包含 `Mcp-Session-Id`。
3. 客户端在后续请求头中携带 `Mcp-Session-Id`。
4. 客户端收到初始化响应后，发送 `initialized` 通知。
5. 初始化完成后即可调用 `tools/list`、`tools/call` 等 MCP 协议方法。

### 1.2 Token 规则

- 在流水线平台**个人中心**生成 API Token。
- 请求头必须包含 `X-User-Tokens: <value>`。
- `<value>` 必须非空、非占位符（如 `${TOKEN}`、`<your-token>`）、长度至少 8 位。
- Token 为空或占位符会导致“假连接”：客户端显示已连接，但调用 tool 时 401/403。
- Token 属于敏感信息：只用于写入用户本机 MCP 配置。用户通过会话提供 Token 时，skill 只将其用于注册，不回显 Token，也不要写入仓库、`SKILL.md`、`USAGE.md` 或公开聊天记录。
- 不要用 `--bearer-token-env-var` 替代 `X-User-Tokens`，除非服务端明确支持 `Authorization: Bearer`。

### 1.3 注册与验证（按客户端选择）

同一时间只需注册当前使用的客户端。默认地址为 `https://devops.ks1.wezhuiyi.com/mcp`；仅当用户主动提供其他地址时才替换。

#### Claude Code

1. 执行 `claude mcp list`，检查是否包含 `pipeline-integration-mcp` 且状态为 `connected`。
2. 未注册或状态异常时，执行：

   ```bash
   claude mcp add --transport http -H "X-User-Tokens: <token>" -s user pipeline-integration-mcp https://devops.ks1.wezhuiyi.com/mcp
   ```

3. 注册后**停止当前流程**，提示用户执行 `/clear` 或退出当前窗口重新进入，刷新会话并加载 MCP tools。
4. 用户刷新会话后，再次执行 `claude mcp list` 确认状态为 `connected`，然后进入工具发现流程。

#### Codex

1. 由 skill 执行 `codex mcp list`，确认 `pipeline-integration-mcp` 存在、状态为 `enabled`。
2. 用户说“调用 devops-mcp-invoker 注册 MCP，token 是 <token>”时，由 skill 代为注册；不要要求用户自行执行 `codex` 命令，也不要要求用户手工编辑 `config.toml`。未注册或缺少 `X-User-Tokens` 时，由 skill 执行：

   ```bash
   codex mcp add pipeline-integration-mcp --url https://devops.ks1.wezhuiyi.com/mcp --header "X-User-Tokens: <token>"
   ```

3. 最新版 Codex 会通过 `--header` 自动写入 `http_headers`，无需手工编辑 `config.toml`。如果提示不支持 `--header`，或执行后没有生成 `http_headers`，告知用户先将 Codex 升级到最新版，再重新发起注册；不要退回到手工编辑 `config.toml`。

   - `<token>` 替换为真实 Token，不要把真实 Token 回显到回复或提交到仓库。
   - 注册命令由 skill 执行，不要求用户复制或运行该命令。
   - Codex 会话中的 MCP tool 名称可能把 server 名中的 `-` 规范化为 `_`，例如显示为 `mcp__pipeline_integration_mcp` 命名空间，这属于正常现象；以当前会话实际暴露的 tool 名称为准。

4. 首次注册后**停止当前流程**，提示用户重启 Codex 或新建会话，让配置生效。
5. 用户刷新会话后，由 skill 再次执行 `codex mcp list` 确认状态为 `enabled`，然后进入工具发现流程；不要让用户自行执行检查命令。

### 1.4 刷新会话与假连接处理

- **Claude Code**：首次注册后必须 `/clear` 或退出重进；未刷新前禁止用 `python`、`curl`、`wget`、PowerShell 或任何方式直接访问 MCP endpoint 尝试获取 tools。
- **Codex**：首次注册后必须重启 Codex 或新建会话；未刷新前同样禁止直接访问 MCP endpoint 探测 tools。
- 若客户端显示已连接但调用 tool 返回 401/403/空结果：
  1. 停止后续操作。
  2. 告知用户属于假连接，Token 无效或已过期。
  3. 要求用户重新生成 Token，并由 skill 按当前客户端重新注册。
  4. 刷新会话后重新检查连接状态。

# DevOps MCP Invoker - References: 常见错误速查

> **必读说明（Read First）**
>
> 本文件是 `SKILL.md` 的**执行级细节补充**，对应 [SKILL.md 常见错误处理](../SKILL.md#常见错误处理)。
> **遇到对应错误场景时，先按本表处理，不要自行发明降级方案。**
>
> [← 返回 SKILL.md](../SKILL.md)

---

## 6. 常见错误速查

| 错误场景 | 处理方式 |
|----------|----------|
| MCP server 未注册或未连接 | 提示用户说“调用 devops-mcp-invoker 注册 MCP，token 是 <token>”，由 skill 按 [REFERENCES-CONNECTION.md §1](./REFERENCES-CONNECTION.md#1-mcp-连接与注册细节) 代为注册；不要让用户自行执行 `codex` 命令或编辑配置文件；注册后刷新会话 |
| token 无效或过期/为空/占位符 | 提示用户重新在流水线平台个人中心生成真实 token，并说“调用 devops-mcp-invoker 注册 MCP”；由 skill 重新注册 |
| 假连接 | 要求用户重新提供真实 token，由 skill 重新注册，不要要求用户修改配置文件 |
| Codex 已注册但缺少 `X-User-Tokens` | 提示用户重新说“调用 devops-mcp-invoker 注册 MCP，token 是 <token>”，由 skill 代为重新注册；不要让用户自行执行 `codex` 命令或编辑配置文件；提示不支持 `--header` 时先升级 Codex |
| 缺少 `project_id`/`env_id` | 优先解析 `pipeline_url`，否则询问用户 |
| MCP 返回多个匹配容器/pod/应用 | 以列表形式展示，让用户选择 |
| 查询 CI 编译失败或超时 | 最多静默重试 1 次，业务错误不重试 |
| 编译失败但当前仓库与 `code_repo` 不一致 | 停止自我修复，展示日志链接，提示切换仓库 |
| git 提交或推送失败 | 停止自我修复，报告错误 |
| 自我修复 3 次上限仍失败 | 停止，报告人工介入 |
| 升级后长时间 `Updating` | 15 分钟后停止，提供日志链接 |
| 用户请求查看冒烟日志但环境未启用 | 直接告知"该环境未启用冒烟测试" |

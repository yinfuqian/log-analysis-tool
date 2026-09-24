# Jira 接口与评论实操（jira-code）

本技能对 Jira 只做三件事：读单子、下载附件、读写那一条进度评论。所有调用都走 `scripts/jira-cli.mjs` 或 `scripts/jira.mjs`，不要自己拼 HTTP 请求。

## 1. 认证与地址

- 认证头：`Authorization: Bearer <JIRA_TOKEN>`（Jira Server / Data Center 的 PAT）。容器内后端会注入并锁定 `JIRA_TOKEN` 与 `JIRA_BASE_URL`（`SKILLRUN_ENV_LOCKED=1`）：只用环境变量，不读令牌文件，也不接受 `--token` / `--base-url` 覆盖。
- 地址：`JIRA_BASE_URL`，未配置时回落到脚本内置默认值。自检结果里的 `baseUrlSource` 会说明地址来自哪里；**如果显示「内置默认值」，说明没配对环境变量，动手前先确认站点**（生产与测试站点的单号可能同名）。
- 每次请求都带 `X-Atlassian-Token: no-check`，附件类接口缺这个头会被 XSRF 拦截。

```bash
node scripts/jira-cli.mjs selftest
```

自检里「校验令牌」返回 401 只表示令牌无权访问 `/myself`，**不等于令牌失效**：只要「访问 Jira」步骤成功，就改用真实单号验证取数。

## 2. 常用接口

| 用途 | 接口 |
|---|---|
| 读取单子 | `GET /rest/api/2/issue/{KEY}?expand=names,renderedFields,schema` |
| 读取全部评论 | `GET /rest/api/2/issue/{KEY}/comment` |
| 新增评论 | `POST /rest/api/2/issue/{KEY}/comment`，体为 `{"body": "..."}` |
| 更新评论 | `PUT /rest/api/2/issue/{KEY}/comment/{ID}`，体为 `{"body": "..."}` |
| 下载附件 | `GET /rest/api/2/attachment/content/{ID}`（附件对象里的 `content` 字段就是该地址） |
| 权限预检 | `GET /rest/api/2/mypermissions?permissions=ADD_COMMENTS,CREATE_ATTACHMENTS` |

`jira.mjs` 的 `getIssue()` 会自动把 `fields.comment` 里没带全的评论补一次全量请求，所以 `issue.comments` 是可用的完整列表。

## 3. 评论写入实操

- 评论用 Jira wiki 标记：`h4.` / `h5.` 标题、`*粗体*`、`#` 有序列表。不要提交 Markdown 表格。
- **本技能的评论由 `progress.mjs` 统一维护**，不要用 `jira-cli.mjs comment` 手工新增进度评论 —— 那会绕过「一条单子一条评论」的约定。
- 校验写入结果：

```bash
node scripts/jira-cli.mjs comments <KEY|URL>
```

输出里应有且只有一条包含 `jira-code:progress:<KEY>` 标记的评论，且 `updated` 时间随心跳前进。

## 4. 读取开发方案附件

```bash
node scripts/jira-cli.mjs attachments <KEY|URL> work/jira-code/<KEY>/attachments
node scripts/plan.mjs find work/jira-code/<KEY>/attachments
python scripts/extract.py work/jira-code/<KEY>/attachments --out work/jira-code/<KEY>/plan.txt
```

- `downloadAttachments` 会逐个下载并返回 `{filename, path, savedSize}`；单个文件失败时该项带 `error` 字段，**不要静默跳过**，要在评论/总结里说明。
- 附件名里的特殊字符会被替换成 `_`；`extract.py` 会递归解析压缩包（`__unpacked` 目录）。
- 解析失败的附件如实记为「无法解析」，不要凭文件名猜内容。

## 5. 故障排查

| 现象 | 原因与处理 |
|---|---|
| `HTTP 401 必须登录` | 令牌缺失或失效；先 `selftest`，确认 `JIRA_TOKEN` 是否注入到容器 |
| `HTTP 403` 且提示 XSRF | 缺少 `X-Atlassian-Token: no-check`；不要手写请求，改用技能脚本 |
| `ADD_COMMENTS=false` | 令牌没有评论权限；`fail` 时说明「无法写评论」，并把结论写进对话总结 |
| 附件 `404` | 附件已被删除；按「方案缺失」处理并中断 |
| 单号解析失败 | 传入的既不是 `KEY` 也不是包含 `/browse/KEY` 的链接；让调用方给正确链接 |
| 评论数比预期多 | 可能是历史遗留评论；按标记定位最新一条继续更新，不要删除既有评论 |

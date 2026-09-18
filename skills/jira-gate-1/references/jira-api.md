# Jira 取数与写评论细节

面向 `jira-gate-1` skill 的实现说明。基础地址：`https://jira.in.wezhuiyi.com`（Jira 10.3.9 Server / Data Center，站点名"Jira-追一研发管理系统"）。

## 1. 为什么必须走 node_repl

- Codex 的 PowerShell 沙箱无法建立 TLS 连接（报 `安全包中没有可用的凭证` / `SSL connection could not be established`），即便放通网络权限也一样，因此**不能用 `Invoke-WebRequest` / `curl` 访问 Jira**。
- `node_repl` 的 Node 进程不受该限制，`fetch` 可正常访问 Jira。
- `node_repl` 内的约束：没有 `process`（读不到环境变量）、不支持静态 `import`、`eval` 被禁用。因此 skill 脚本一律用 `await import()` 动态加载，令牌从文件读取。
- `node_repl` 会缓存已导入模块；改了脚本后用 `import("file:///...jira.mjs?v=时间戳")` 强制重新加载。

## 2. 认证

### 2.1 个人访问令牌（首选）

创建：Jira → 右上角头像 → 个人访问令牌 → 创建令牌。请求头：`Authorization: Bearer <token>`。

存放位置（`jira.mjs` 的查找顺序）：

1. `<skill 目录>\.jira-token`、`.jira-token.txt`、`jira-token.txt`
2. `<skill 目录>\..\jira-token.txt`（即 `~/.codex/skills/jira-token.txt`）
3. `~/.codex/jira-token.txt`
4. `~/.codex/jira\token.txt`
5. `~/.codex/jira\config.json`，内容形如 `{"token":"...","baseUrl":"https://jira.in.wezhuiyi.com"}`

文件内容为单行令牌即可，也支持 `JIRA_PAT=xxx` 形式。脚本按行读取第一行非空内容，不会回显令牌。

### 2.2 匿名读取的边界

公开项目的单子可以不认证读取（实测 `CALL-1446`、`CALL-1178` 返回 200）；非公开项目（如 `ZY20260061-*`）匿名读取返回 `HTTP 401 您没有查看特定问题的权限；必须登录`。写评论必须认证。

## 3. 常用接口

| 用途 | 方法与路径 |
|---|---|
| 连通性与版本 | `GET /rest/api/2/serverInfo`（无需认证） |
| 当前账号（校验令牌） | `GET /rest/api/2/myself` |
| 需求单全量字段 | `GET /rest/api/2/issue/{KEY}?expand=names,renderedFields,schema` |
| 当前用户对某单的权限（写评论前预检） | `GET /rest/api/2/mypermissions?issueKey={KEY}` |
| 按父单查子任务 | `GET /rest/api/2/search?jql=parent%20%3D%20{KEY}` |
| 全部评论（超过一页时） | `GET /rest/api/2/issue/{KEY}/comment` |
| 写评论 | `POST /rest/api/2/issue/{KEY}/comment`，Body `{"body":"..."}` |
| 改评论 | `PUT /rest/api/2/issue/{KEY}/comment/{id}` |
| 附件下载 | `GET {attachment.content}`，需带同一认证头 |

固定请求头：`Accept: application/json`、`X-Atlassian-Token: no-check`。

Jira 错误响应形如 `{"errorMessages":["..."],"errors":{...}}`，`jira.mjs` 会把它拼成可读错误信息。

## 4. 字段映射

`expand=names` 会返回 `names` 映射（`customfield_xxx` → 中文名），`jira.mjs` 用它把自定义字段翻译成中文键，例如：

- `产品归属`、`客户名称`、`需求实现类型`、`问题反馈来源`、`是否首次`、`批次编号`、`问题发现产品`、`项目阶段`、`Story Points`、`Rank`（噪音，渲染时跳过）、`Development`（噪音）。

需求单常见标准字段：`issuetype`、`summary`、`description`、`status`、`priority`、`resolution`、`reporter`、`assignee`、`labels`、`components`、`versions`（影响的版本）、`fixVersions`（修复的版本）、`issuelinks`（问题链接）、`subtasks`（子任务，注意是复数）、`attachment`、`comment`、`timetracking` / `timeoriginalestimate`（工时）。

工时要注意：`timeoriginalestimate` 为空表示**没有评估工时**，是 checklist §6.7.1 的直接证据。

## 5. 浏览器兜底通道的操作要点

1. `cua.createBrowserTab("iab", "https://jira.in.wezhuiyi.com/browse/KEY", { visible: false })` 打开单子。
2. `await tab.playwright.evaluate(() => document.body.innerText)` 取正文——描述、详情字段、附件列表、问题链接、子任务、评论区都在其中。
3. 附件下载：定位附件链接后触发下载，再到下载目录跑 `extract.py`（压缩包会自动解压，见 §6.6）。
4. 写评论：在评论区输入文本并提交（这是对外发布内容，写入前必须让用户确认）。
5. 浏览器里访问 `/rest/...` 会被拦截（`net::ERR_BLOCKED_BY_CLIENT`），只能读页面。

## 6. 实测踩过的坑（已修复，改脚本时不要回退）

1. **子任务字段名是 `subtasks`（复数），不是 `subtask`**。写错时 `fields.subtask` 为 `undefined`，会把有 6 个子任务的单子误判成"未拆解子任务"，直接误伤 checklist §6.7.1。
   实测 `ZY20260061-3343`：`fields=subtask` 返回空，`fields=subtasks` 返回 6 条。
   双保险：`getIssue()` 在 `subtasks` 为空时再用 JQL `parent = {KEY}` 查一次（见 `fetchSubtasksByParent()`）。
2. **`extract.py` 必须先把 stdout 改成 UTF-8**。Windows 控制台默认 GBK，附件里出现 emoji（例如 tts 接口文档里的 🌐）时 `print` 会抛 `UnicodeEncodeError`，而且异常发生在写 `--out` 之前，会连带丢掉输出文件。脚本里已用 `force_utf8_stdout()` 处理。
3. **描述里的 Jira wiki 标记要清理**。`{color:#de350b}…{color}`、`[^附件名]`、`{code}` 会污染描述文本；`cleanWikiMarkup()` 负责清理，但保留 `||表头||` 这类有信息量的表格语法。
4. **浏览器访问 `/rest/...` 会被拦截**（`net::ERR_BLOCKED_BY_CLIENT`），浏览器通道只能读页面和写评论，不能直接调 API。
5. **`mypermissions` 的 `permissions` 过滤参数在本站会被忽略**，接口会返回全量权限列表；从中读 `ADD_COMMENTS`、`EDIT_ISSUES`、`TRANSITION_ISSUES` 即可。
6. **压缩包附件必须"先解压再解析"**。需求单常把 PRD / 原型 / Overview 打包成 `.rar` 或 `.zip`，直接解析压缩包只会得到乱码或"无法解析"。`extract.py` 会自动识别 `.zip / .rar / .7z / .tar / .tar.gz / .tgz / .gz / .bz2 / .xz`，解压到附件目录下的 `__unpacked\` 后递归解析，输出用 `压缩包名/内部路径` 标注来源。
   `.rar` 没有可用的纯 Python 实现，本机也常缺 WinRAR / 7-Zip：脚本按 `tar`（Windows 自带 bsdtar，实测支持 RAR5）→ `7z` → `7za` → `unrar` 顺序降级。实测 CALL-1941 的 `.rar` 三件套（PRD_DELIVERY / Prototype / Overview）可正常解出，中文目录名正常。
   解压失败时输出 `[压缩包解压失败]` 并列出尝试过的命令与报错，**此时必须记为"附件无法解析"，不能当成"附件没有内容"，也不要臆测包内内容**。
   同一目录内的 `__unpacked` 在遍历时会被跳过，不会重复解析；同名解压结果自动加 `-2` 后缀，不覆盖上一次结果。

## 7. 写评论前的权限预检

写评论是有副作用的外部动作，落笔前先用一次只读接口确认权限：

```javascript
const p = await j.request("GET", `/rest/api/2/mypermissions?issueKey=${key}`);
nodeRepl.write(["ADD_COMMENTS", "EDIT_ISSUES", "TRANSITION_ISSUES"].map(n => `${n}=${p.permissions[n].havePermission}`).join(", "));
```

实测 `ZY20260061-3343`：`ADD_COMMENTS=true`、`EDIT_ISSUES=true`、`TRANSITION_ISSUES=true`。若 `ADD_COMMENTS=false`，不要反复重试，直接告知用户缺少评论权限。

## 8. 评论写入实操

- 评论模板与 Jira wiki 标记对照见 `SKILL.md`「输出模板」节；**评论正文用 Jira wiki 标记，不要提交 Markdown 表格**，否则会显示成原始符号。
- 评论只列检查点：一行难度结论 + 检查项清单；每项行首必须有标记——通过写 `(/)`（绿勾），不通过写 `(x)`（红叉）。不通过项每条一行、80 字以内；判定过程与难度维度留在对话回复里。
- 写入后读回验证，确认渲染正常、无截断：

```javascript
const c = await j.addComment(key, text);
const back = await j.getIssue(key);
const last = back.comments[back.comments.length - 1];
nodeRepl.write(last.id + " | " + last.author + " | " + last.body.slice(0, 120));
```

- Jira wiki 表格的单元格内容必须在一行内写完；单元格里出现 `|` 需转义为 `\|`，否则表格列会错位。
- 评论正文中避免出现未转义的花括号组合（`{color}` 之类会被当作宏）。
- 结论只以评论留痕，不生成报告文档；本地仅保留附件与解析中间文件。

## 9. 故障排查

| 现象 | 原因与处理 |
|---|---|
| `SSL connection could not be established` | 在 PowerShell 里访问 Jira 了；改到 `node_repl` 执行 |
| `process is not defined` | 脚本里出现了静态 `import` 或 `process.xxx`；改为 `await import()`，令牌从文件读 |
| `HTTP 401 必须登录` | 令牌缺失/失效，或访问了非公开项目；先 `selftest()`，必要时用浏览器通道 |
| `HTTP 403` 且带 XSRF 提示 | 缺 `X-Atlassian-Token: no-check` 头 |
| 附件下载 404 | 单子里的附件已被删除；按"附件缺失"记录，不要静默跳过 |
| 输出里有 `[压缩包解压失败]` | 本机没有可用解压命令；如实记为"附件无法解析"，并请产品经理直接上传解压后的文件 |
| 评论数与 `fields.comment.total` 不一致 | `getIssue()` 会自动再拉一次 `/comment` 全量接口 |

## 10. 门禁字段与工作流门禁（Jira 管理端配置）

### 10.1 为什么不能在工作流里直接调 AI

工作流校验器/条件必须是**同步、确定性、亚秒级**的；AI 预检是异步、非确定性的，还要读附件。因此正确架构是两段式：

1. **AI 预检**（本 skill）：读需求单 → 判定 → 写评论 → 用 `setGateResult()` 把结论回写到 Jira 字段。
2. **工作流门禁**（Jira 配置）：流转校验只读那个字段，不调用 AI。

### 10.2 需要 Jira 管理员做的事

用管理员账号（本 skill 的令牌**没有**管理员权限，做不了这三件事）：

1. **建自定义字段**（管理 → 问题 → 自定义字段），类型建议：

| 字段名 | 类型 | 取值 |
|---|---|---|
| `G1准入结论` | 单选列表 | `未检查` / `通过` / `不通过` / `豁免` |
| `G1需求难度` | 单选列表 | `高` / `中` / `低` |
| `G1预检时间` | 日期时间 | — |

  字段名可自定义，但要和 `config.json` 里的 `gateResultField` 等保持一致。

2. **加入屏幕**：把三个字段加到 `故事` / `客户用户故事` 的**查看**和**编辑**屏幕上（REST 写字段要求字段在该问题类型的编辑屏幕上）。

3. **加流转门禁**：在「→ 开发设计中」这条流转上二选一：

| 方案 | 配置 | 效果 | 依赖 |
|---|---|---|---|
| A. 隐藏按钮 | 条件（Condition）→ 内置 **Value Field**，`G1准入结论 = 通过` | 不满足时按钮直接不显示 | 无，Jira 原生支持 |
| B. 拦截并报错 | 校验器（Validator）→ ScriptRunner `Simple Scripted Validator` / JMWE 条件校验 | 按钮可见，点击后报错提示去评论区看缺口 | 需要 ScriptRunner 或 JMWE |

  推荐 **B**（能告诉用户为什么不能流转，整改闭环更短）；两种都不影响 REST 与批量流转路径，因为条件和校验器在所有路径上都会执行。

### 10.3 两个必须堵的漏洞

1. **结论可被手工绕过**：任何有「编辑问题」权限的人都能把 `G1准入结论` 手动改成 `通过`。
   - 轻量缓解：字段配置里把 `G1准入结论` 设为只读，让 UI 改不了（REST 仍可写，需实测确认）。
   - 强校验：校验器里额外读该字段的改动记录，要求**最后一次修改者必须是 AI 专用账号**，否则拒绝流转。
2. **结论会过期**：AI 判完 `通过` 后，产品经理又改了 PRD 或换了附件，字段仍挂着 `通过`。
   - 缓解：用 ScriptRunner 监听器（Issue Updated），在**附件增删改或描述变更**时把 `G1准入结论` 重置为 `未检查`，强制重新预检。

### 10.4 其他运营建议

- **保留人工豁免通道**：加 `豁免` 取值，只允许产品架构师角色设置，避免 AI 误判把需求彻底卡死。
- **先观察再收紧**：建议先用方案 B 的「警告模式」跑 1~2 个迭代，统计误判率，再切成硬门禁。
- **难度可以联动**：`G1需求难度 = 高` 时可额外要求技术方案评审，或多挂一个校验条件。

### 10.5 相关函数

```javascript
const rf = await j.resolveGateFields();     // 探测字段是否存在：{ fields, missing, configSource }
const g  = await j.getGateResult("CALL-1940");  // 读回当前值
const r  = await j.setGateResult("CALL-1940", { result: "不通过", difficulty: "高" });
const d  = await j.setGateResult("CALL-1940", { result: "通过" }, { dryRun: true });  // 只算不写
```

- `setGateResult()` 在字段不存在时返回 `{ ok:false, skipped:true, reason, hint }`，**不抛异常**，便于优雅降级。
- 单选字段写成 `{ value: "通过" }`，其他类型写字符串；`G1预检时间` 默认写入当前时间。
- 字段名覆盖方式（`~/.codex/jira/config.json`）：

```json
{
  "token": "...",
  "gateResultField": "G1准入结论",
  "gateDifficultyField": "G1需求难度",
  "gateCheckedAtField": "G1预检时间"
}
```

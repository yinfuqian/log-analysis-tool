---
name: jira-code
description: 读取 Jira 单上的「开发方案」附件，确定 GitLab 仓库与基线分支，从基线分支拉出 feature/<KEY> 分支并把方案实现成代码、提交并推送到远端；全程只用一条自动刷新的 Jira 评论汇报进度与异常。当用户要求「按开发方案实现这个需求」「照方案写代码并推分支」「jira-code 跑一下这张单」时使用。
---

# jira-code：按开发方案实现代码

把一张 Jira 需求单上的「开发方案」附件读成代码改动：找到方案里写的 GitLab 仓库与基线分支 → 拉出 `feature/<KEY>` 分支 → 按方案写代码 → 提交并推送。整个过程**不等人工确认**，并在 Jira 单上维护**唯一一条**进度评论，每 5 分钟自动刷新。

## 1. 能力与硬边界

**本技能做**：读单子与开发方案、在 feature 分支上写代码、提交、推送、用一条评论汇报进度与异常。

**本技能不做**（做了就是错误执行）：

- 不改单子状态、不流转工作流（`transition` 相关能力刻意没有开放）。
- 不写自定义字段（门禁字段等一律不碰）。
- 不上传附件、不改单子标题与描述。
- 不动基线分支（基线分支只读）：不向 `main`/`master`/`release/*` 等基线分支直接提交或强制推送。
- 不新增第二条进度评论：一条需求单只允许一条进度评论（详见 §4）。
- 不臆造方案里没有的仓库、分支、需求内容。

**交付物**就是两样：远端仓库里的 `feature/<KEY>` 分支，以及 Jira 单上的那一条评论。本地文件都只是中间产物：
推送成功后必须用 `git-flow.mjs cleanup` 把刚拉下来的检出目录删掉，**不在工作区留代码副本**（只对推送成功的目录做清理，
没推上去的目录要保留下来便于排查）。

## 2. 运行环境与凭据

运行环境是服务器容器：没有桌面工具，所有操作都用 shell 执行本技能自带脚本（`node <技能目录>/scripts/*.mjs`）。

- 技能目录（容器内只读）：`/data/skills/jira-code`；下文用 `<技能目录>` 代指。
- 工作区：进程当前目录（技能任务的工作目录），代码检出与状态文件都放这里，不要写进技能目录。

| 环境变量 | 用途 | 缺失时的后果 |
|---|---|---|
| `JIRA_TOKEN` | Jira 个人访问令牌，`jira-cli.mjs` 读取 | 读不到单子，无法执行 |
| `JIRA_BASE_URL` | Jira 站点地址 | 回落到内置默认值，可能连错站点 |
| `GITLAB_PRIVATE_TOKEN` | GitLab 访问令牌（推送必需，需要写仓库权限） | 只能拉取，推送会失败 |
| `GIT_USER` / `GIT_PASSWORD` | 上没有令牌时的账号密码兜底 | — |
| `GIT_BASE_URL` | GitLab 站点地址，方案里只写「group/repo」时用来补主机 | 需要显式传 `--base-url` |

先做一次自检，把凭据状态确认清楚再动手：

```bash
node <技能目录>/scripts/jira-cli.mjs selftest
node <技能目录>/scripts/git-flow.mjs creds      # 只回显凭据来源，不会打印令牌本身
```

凭据口径：令牌只作为本次 git 命令的临时参数传入，**不会写进 `.git/config`，也不会出现在任何输出里**；不要自己拼 `https://user:token@...` 去 clone，也不要让 git 弹出交互式登录（脚本已禁用交互提示）。

## 3. 标准执行流程

**顺序固定，中间不要停下来等人工确认**；只有 §3.4 的「信息不足」分支才允许中断流程。

### 3.1 读取单子

```bash
node <技能目录>/scripts/jira-cli.mjs get <KEY|URL>
```

`<KEY>` 就是单号（URL `/browse/` 后面那一段，例如 `ZYSQ-95`），也是分支名与评论里的标识。取到单号后立刻用它启动进度心跳（§3.5），让 Jira 上尽早能看到「开始处理」。

### 3.2 下载并解析开发方案附件

```bash
# 下载附件到工作区
node <技能目录>/scripts/jira-cli.mjs attachments <KEY|URL> work/jira-code/<KEY>/attachments
# 找出「开发方案」文件（按文件名关键词匹配）
node <技能目录>/scripts/plan.mjs find work/jira-code/<KEY>/attachments
# 转成纯文本（压缩包会自动解压；docx/pdf/xlsx 都能解析）
python <技能目录>/scripts/extract.py work/jira-code/<KEY>/attachments --out work/jira-code/<KEY>/plan.txt
```

`extract.py` 优先使用容器内已装的解压工具（bsdtar / 7z / unzip）。**不要**自行 `apt-get`、`pip`、`npm` 安装工具；解压或解析失败时如实记为「方案无法解析」并按 §3.4 处理。

### 3.3 提取仓库与基线分支

```bash
node <技能目录>/scripts/plan.mjs candidates work/jira-code/<KEY>/plan.txt
```

输出 JSON：`repos`（仓库候选）、`branches`（分支候选）、`pairs`（方案里写成一组的「仓库 + 分支」）。选取规则，按优先级：

1. **优先用 `pairs`**：方案里成对写了仓库与分支时，逐对处理（方案可能涉及多个仓库，那就每个仓库各建一条同名的 `feature/<KEY>` 分支）。
2. `pairs` 为空时，只有在 `repos` 与 `branches` **各自只有一个候选**的情况下才能配对。
3. 其余情况（多仓库多分支且没有明确对应关系）→ 按 §3.4 中断，并在评论里列出候选清单请人确认。

候选里带 `confidence: "high"` 的优先；`GIT_BASE_URL` 存在时，方案里只写 `group/repo` 的路径写法可以直接用。
**只允许从 `plan.mjs` 的输出里挑**，不许自己拼仓库地址或分支名。

### 3.4 信息不足：评论 + 中断

出现下列任意一种情况，就**不再往下走**（不建分支、不写代码、不推送）：

- `plan.mjs find` 失败：单子上没有开发方案附件（退出码 1）。
- `plan.mjs candidates` 失败：方案里没有仓库信息或没有分支信息（退出码 1）。
- 仓库与分支无法配对（§3.3 第 3 条）。

处理方式：把原因写进那条进度评论并置为「已中断」，然后结束任务：

```bash
node <技能目录>/scripts/progress.mjs fail --state work/jira-code/<KEY>/progress.json \
  --message "未在开发方案里找到仓库与分支信息，已中断：<具体缺什么>"
```

中断说明要写清楚**缺什么、需要谁补什么**（例如「方案只有实现要点，没有写仓库与目标分支，请补充后重新触发」）。这类中断**不要**新建评论，也不要重复触发第二次。

### 3.5 启动进度心跳

```bash
node <技能目录>/scripts/progress.mjs start --issue <KEY|URL> \
  --state work/jira-code/<KEY>/progress.json \
  --stage "已读取开发方案" --summary "<单子标题>" \
  --repo work/jira-code/<KEY>/<仓库目录名> --repo-label "<group/repo>" --branch feature/<KEY>
```

`start` 会立刻发布一次评论，并 fork 一个后台心跳进程，默认**每 5 分钟**刷新一次（`--interval` 可调，仅自测用）。心跳会自己带上代码改动快照（分支、提交数、未提交文件数），所以即使 agent 在长时间写代码，Jira 上的进度也会往前推进。

### 3.6 拉取 feature 分支

```bash
node <技能目录>/scripts/git-flow.mjs prepare \
  --repo "<方案里的仓库>" --base "<方案里的基线分支>" --key <KEY> \
  --dir work/jira-code/<KEY>/<仓库目录名> [--base-url "$GIT_BASE_URL"]
```

分支命名是硬性规则：**`feature/<KEY>`**（KEY 为单号，例如 `feature/ZYSQ-95`），由脚本统一生成，不要自己改名、不要加日期或人名后缀。脚本会：初始化检出目录（保留干净 origin）→ 拉取基线分支 → 基于它创建/重置 `feature/<KEY>` → 配好提交身份。

基线分支不存在或拉取失败时，脚本会退出码 1 并列出远端现有分支；此时**不要**擅自换一个分支继续，按 §3.8 记为异常中断。

### 3.7 写代码、提交、推送

按方案实现代码（见 §5 编码要求），然后：

```bash
node <技能目录>/scripts/git-flow.mjs status --dir work/jira-code/<KEY>/<仓库目录名>
node <技能目录>/scripts/git-flow.mjs commit --dir work/jira-code/<KEY>/<仓库目录名> \
  --message "feat(<KEY>): <一句话说明>"
node <技能目录>/scripts/git-flow.mjs push --dir work/jira-code/<KEY>/<仓库目录名>
```

推送使用令牌作为临时参数，默认普通 push；**禁止 `--force`**，只有在需要覆盖自己刚推上去的分支时才允许 `--force-with-lease`。

多个仓库时，对每个仓库重复 §3.6–§3.7（`--dir` 换成各自目录）。

推送成功后，立刻把这个检出目录删掉，不要让代码留在工作区：

```bash
node <技能目录>/scripts/git-flow.mjs cleanup --dir work/jira-code/<KEY>/<仓库目录名> \
  --key <KEY> --verify-remote
```

`cleanup` 只认 `prepare` 写下的标记文件（`<检出目录>.jira-code-checkout.json`），只删本技能自己拉的目录；
`--verify-remote` 会先确认远端确实有这个 feature 分支，避免代码没推上去就把本地删了。
如果有提交还没推送、或还有未提交改动，`cleanup` 会**拒绝删除**（原因 `unpushed-commits` / `uncommitted-changes`），
此时先补推送；确实要丢弃时用 `--force`，并在评论里说明丢弃了什么。

多个仓库时逐个清理；收尾前工作区里不应再有本次拉下来的仓库目录。

### 3.8 收尾

成功：先按 §3.7 清理完检出目录，再 `finish`（写清分支、提交、仓库，并说明本地已清理）；
异常：`fail`（写清失败环节与原因）。**两者都必须调用**，否则心跳会一直留在后台。
异常中断时**不要**删检出目录，保留现场便于排查。

```bash
node <技能目录>/scripts/progress.mjs finish --state work/jira-code/<KEY>/progress.json \
  --message "已推送 feature/<KEY>：<仓库> <提交摘要>"
# 或
node <技能目录>/scripts/progress.mjs fail --state work/jira-code/<KEY>/progress.json \
  --message "推送失败（auth-failed）：GitLab 令牌缺少写权限"
```

`finish` / `fail` 的返回值里 `ok:false` 说明评论没写成功（退出码同时为 1），要在对话总结里如实说明，不要说成已完成。

## 4. 进度与异常评论规范

- **一条单子只有一条进度评论**：评论末尾带固定标记行 `jira-code:progress:<KEY>`，脚本按标记查找，命中就更新那条，命中不到才新建。重复执行本技能、心跳刷新、异常上报都只更新同一条。
- **每 5 分钟自动刷新**：由 `progress.mjs start` 拉起的心跳负责，不需要 agent 自己计时。
- **阶段变化时主动刷新**（不必等心跳）：读方案、建分支、写代码、跑测试、提交、推送、收尾这些里程碑各调一次：

```bash
node <技能目录>/scripts/progress.mjs update --state work/jira-code/<KEY>/progress.json \
  --stage "编写代码" --step "已完成 5.2 批量删除接口，正在写单测"
```

推送完成、检出目录清理掉之后，也补一条明细，让 Jira 上能看出工作区已经清干净：

```bash
node <技能目录>/scripts/progress.mjs update --state work/jira-code/<KEY>/progress.json \
  --stage "推送完成" --step "已推送 feature/<KEY> 并清理本地检出目录"
```

- **异常写进同一条评论**：中途出错先在评论里留痕再继续修（`update --step "..."`），确认无法继续时用 `fail --message "<原因>"` 收尾；不要新开评论，也不要把错误咽下去。
- 评论内容保持简短：阶段 + 最近几条明细 + 分支 + 时间 + 异常原因即可，不要贴大段代码或完整日志。
- 评论用 Jira wiki 标记（`h5.` 标题、`*粗体*`），不要写 Markdown 表格。

## 5. 编码要求

1. **按方案实现**：方案里写了什么就实现什么；方案没写清楚的地方按仓库现有代码风格与最小改动原则处理，不擅自扩大范围。
2. **中途不要停下来等确认**：不要为了「确认要不要这样写」而暂停任务，一次把代码写完。
3. **尊重现有代码**：沿用仓库的目录结构、命名与依赖，不重构无关代码，不改无关文件，不删除他人代码。
4. **必须有验证动作**：能跑构建/测试就跑（`mvn -o test`、`npm test`、`pytest` 等按仓库实际技术栈选择），跑不了就说明原因；不要提交明显编译不过的代码。
5. **提交信息**：`feat(<KEY>): 简述` / `fix(<KEY>): 简述` 形式，一次提交聚焦一件事。
6. **不提交敏感信息**：不要把令牌、密码、`.env` 里的真实值写进代码或提交。
7. **改不动就如实说**：仓库拉不下来、没有权限、方案与技术栈不匹配时，按 §3.8 用 `fail` 说明，不要编造「已完成」。

## 6. 交付物与对话总结

完成后用简洁中文总结：单号、仓库、分支（`feature/<KEY>`）、提交（短 SHA + 摘要）、推送结果、评论状态（评论 ID 与当前状态）、以及没做到的部分与原因。

## 7. 自检清单

- [ ] `progress.mjs start` 已执行，Jira 上只有一条带标记的进度评论。
- [ ] 分支名严格是 `feature/<KEY>`。
- [ ] 代码只改在 feature 分支上，基线分支未被改动。
- [ ] 提交信息带单号，不含敏感信息。
- [ ] `git-flow.mjs push` 返回 `ok:true`，且没有使用 `--force`。
- [ ] 推送成功后已用 `cleanup --verify-remote` 删除本地检出目录，工作区没有留下代码副本。
- [ ] `progress.mjs finish`（或 `fail`）已执行，状态与真实结果一致。
- [ ] 没有改动单子状态、没有写自定义字段、没有新增第二条进度评论。

## 8. 故障排查

| 现象 | 原因与处理 |
|---|---|
| `plan.mjs find` 报「附件目录里没有开发方案文件」 | 单子确实没上传方案，或文件名不含关键词；按 §3.4 用 `fail` 中断并列出目录内实际文件 |
| `plan.mjs candidates` 报「没有找到 GitLab 仓库信息 / 分支信息」 | 方案是自然语言描述、没写地址与分支；按 §3.4 中断，不要猜 |
| `git-flow.mjs prepare` 报 `base-branch-not-found` | 方案里的基线分支在远端不存在（可能已合并删除）；按返回的现有分支清单请人确认后中断 |
| `git-flow.mjs prepare` 报 `repo-needs-base-url` | 方案只写了 `group/repo` 且没配 `GIT_BASE_URL`；让部署方补配置或显式传 `--base-url` |
| `git-flow.mjs push` 报 `auth-failed` | 令牌缺失或没有写仓库权限；按 §3.8 中断并说明需要哪种权限 |
| `git-flow.mjs push` 报 `push-rejected` | 目标分支受保护或没有推送权限；不要改用 force，如实上报 |
| `cleanup` 报 `unpushed-commits` | 还有提交没推到远端；先补 `push`，确认远端有分支后再清理 |
| `cleanup` 报 `uncommitted-changes` | 还有代码没提交；先提交推送，或确认无用后 `--force` 并在评论里说明 |
| `cleanup` 报 `not-managed-checkout` / `dir-mismatch` | 目录不是本技能拉的（没有标记文件），不要用 `--force` 绕开，人工确认后再处理 |
| `cleanup` 报 `remote-branch-missing` | 远端没有该 feature 分支，说明代码没推上去；保留目录并如实上报 |
| `progress.mjs` 报「进度评论写入失败」 | Jira 不可达或令牌无评论权限；检查 `selftest` 结果，把失败写进对话总结，不要谎报成功 |
| 评论里出现两条进度评论 | 只应发生在历史遗留数据上；以带标记的最新一条为准继续更新，不要删评论 |
| 心跳进程没有停 | `finish`/`fail` 未调用，或进程被强杀；用 `progress.mjs stop --state <文件>` 手动收尾 |

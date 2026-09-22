# 开发方案的识别规则（jira-code）

`plan.mjs` 只做**候选提取**，选哪一条由技能按 `SKILL.md` §3.3 的规则决定；但候选必须来自脚本输出，禁止自己编地址或分支名。

## 1. 找方案文件：`plan.mjs find <附件目录>`

按文件名关键词打分（越靠前优先级越高）：

`开发方案` → `开发计划` → `技术方案` → `技术设计` → `实现方案` → `设计方案` → `概要设计` → `详细设计` → `技术实现` → `dev-plan` → `devplan` → `develop-plan` → `design` → `方案`

其他规则：

- 图片、视频等非文档类型直接跳过。
- 同关键词下，`.md/.txt/.docx/.pdf/...` 优先于 `.zip/.rar/.7z`（压缩包要先解压，成本更高）。
- 多个同名候选时按文件名排序取第一个，保证结果稳定可复现。
- 没有候选时输出 `{ok:false, reason:"attachment-not-found", entries:[...]}` 并以退出码 1 结束，`entries` 是目录里实际有哪些文件，用于在评论里说明。

## 2. 提候选：`plan.mjs candidates <方案文本文件>`

输出结构：

```json
{
  "ok": true,
  "textSource": ".../plan.txt",
  "baseHost": "code.in.wezhuiyi.com",
  "repos":    [{ "url": "https://code.in.wezhuiyi.com/shop/cart-service.git", "host": "...", "raw": "...", "line": 4, "confidence": "high", "count": 1 }],
  "branches": [{ "name": "release/2.4", "raw": "目标分支：release/2.4", "line": 5, "confidence": "high", "preferred": true, "count": 2 }],
  "pairs":    [{ "repo": "shop/cart-service", "repoRaw": "shop/cart-service", "branch": "release/2.4", "line": 4, "source": "neighbor-line" }]
}
```

### 2.1 仓库候选怎么来的

- `http(s)` 地址：主机名像 GitLab（含 `gitlab`、`code.`、`git.`、`gitee`、`github` 等），或该行出现「仓库/代码库/gitlab/repo」等字样，或地址以 `.git` 结尾；Jira、Confluence、Wiki、文档站等主机直接排除。
- 网页地址会砍掉 `/-/blob/...`、`/-/tree/...` 等文件路径，只留仓库根；统一补成 `.git` 结尾。
- `git@host:group/repo.git` 形式的 SSH 地址原样保留。
- 显式写法：`仓库：shop/cart-service`、`代码库：…`，以及表格写法 `| 仓库 | shop/cart-service |`。

### 2.2 分支候选怎么来的

- 显式写法（最高置信度）：`分支：release/2.4`、`目标分支：…`、`基线：…`、`基于 …`；`目标分支/基线/基于` 会额外标 `preferred: true`。
- 前缀特征（高置信度）：`feature/…`、`release/…`、`hotfix/…`、`develop/…` 等。
- 主干名（中置信度）：`master`、`main`、`develop`、`dev`、`uat`、`prod` 等，**只有该行出现「分支/基线/基于」上下文时才采纳**，避免把普通英文单词当分支。
- 明显是文件名的（带 `.md`、`.java`、`.pdf` 等后缀）会被剔除；`release/2.4` 这种带点号的分支名是合法的，不会被误删。

### 2.3 配对 (`pairs`)

- **同一行**同时出现仓库与分支 → `source: "same-line"`（表格、`仓库：A 分支：B` 这类写法都命中）。
- 仓库行**紧邻下一行**只有分支且下一行没有仓库 → `source: "neighbor-line"`（常见的「项目符号列表」写法）。
- 其他情况不猜配对：由技能按 `SKILL.md` §3.3 决定是「唯一候选直接配对」还是「信息不足 → 中断」。

## 3. 判定与中断口径

- `repos` 或 `branches` 为空 → `ok:false`，`reason` 为 `repo-not-found` / `branch-not-found`，退出码 1 → 技能按 §3.4 评论并中断。
- 有多个仓库或多个分支：优先按 `pairs` 逐对处理（方案可能同时涉及多个仓库）；`pairs` 为空且各自只有一个候选时可以直接配对；否则中断请人确认。
- 任何情况下都**不允许**用「默认分支 master」或相似仓库名去补全缺失信息。

# GitLab 与 Git 操作约定（jira-code）

## 1. 凭据

| 环境变量 | 说明 |
|---|---|
| `GITLAB_PRIVATE_TOKEN` | 首选。GitLab 个人访问令牌，**推送需要写仓库权限**（`write_repository` 或 `api`）；用户名默认用 `oauth2`，可用 `GITLAB_USER` 覆盖 |
| `GIT_USER` / `GIT_PASSWORD` | 兜底：上没有令牌时用账号密码认证 |
| `GIT_BASE_URL` | GitLab 站点地址（例如 `https://code.in.wezhuiyi.com/`）；方案里只写 `group/repo` 时用它补主机 |

```bash
node scripts/git-flow.mjs creds     # 只回显凭据来源与用户名
```

凭据使用规则（脚本已实现，不要绕开）：

1. 令牌只作为**本次命令的临时参数**传给 git，不写进 `.git/config`，也不打印到输出（输出里的 `//user:pass@` 一律脱敏成 `//***@`）。
2. `origin` 始终保存不含凭据的干净地址，方便事后核对来源。
3. 关闭交互式提示（`GIT_TERMINAL_PROMPT=0`），没有凭据时立即失败而不是卡住等人输密码。
4. 网络操作优先使用 `git fetch --no-write-fetch-head`（避免远端地址落进 `FETCH_HEAD`）；老版本 git 会退回普通 fetch，脚本随后擦掉 `FETCH_HEAD` 里的凭据。

## 2. 仓库地址形式

`git-flow.mjs` 支持三种写法：

| 方案里可能写 | 处理 |
|---|---|
| `https://code.in.wezhuiyi.com/shop/cart-service` 或带 `/-/blob/...` 的网页地址 | 规范化成 `https://code.in.wezhuiyi.com/shop/cart-service.git` |
| `git@code.in.wezhuiyi.com:shop/cart-service.git` | 原样使用（需要容器内有可用 SSH 私钥；容器默认只装 git，不装 openssh-client，**优先要求方案提供 https 地址**） |
| `shop/cart-service` | 用 `GIT_BASE_URL` 补主机；缺配置时报 `repo-needs-base-url` |

## 3. 分支约定

- 基线分支：方案里写的分支（`release/2.4`、`develop` 等），只读。
- 工作分支：固定 `feature/<KEY>`，由 `git-flow.mjs prepare --key <KEY>` 生成，**不允许改名**。
- 推送：`git push <仓库> HEAD:refs/heads/feature/<KEY>`，普通推送；禁止 `--force` 覆盖远端分支，必要时才用 `--force-with-lease`。推送分支受保护时会报 `push-rejected`，此时不要去改保护规则，如实上报。

## 4. 常用命令

```bash
node scripts/git-flow.mjs prepare --repo "<仓库>" --base "<基线分支>" --key <KEY> --dir work/jira-code/<KEY>/repo
node scripts/git-flow.mjs status --dir work/jira-code/<KEY>/repo
node scripts/git-flow.mjs commit --dir work/jira-code/<KEY>/repo --message "feat(<KEY>): <简述>"
node scripts/git-flow.mjs push  --dir work/jira-code/<KEY>/repo
# 推送成功后清理本地检出（先确认远端真的有这个分支）
node scripts/git-flow.mjs cleanup --dir work/jira-code/<KEY>/repo --key <KEY> --verify-remote
```

`prepare` 是幂等的：检出目录已存在时不会重新 clone，只重新拉基线分支并重建 `feature/<KEY>`；所以在重跑时可以放心再执行一次。

`cleanup` 只删本技能 `prepare` 写下的标记目录（标记文件为 `<检出目录>.jira-code-checkout.json`，故意放在检出目录**外面**，免得被 `git add -A` 提进仓库）。默认情况下，只要还有未推送的提交（`unpushed-commits`）或未提交的改动（`uncommitted-changes`），它就拒绝删除；加 `--verify-remote` 还会先确认远端存在该 feature 分支，没有则报 `remote-branch-missing` 并保留本地目录。确实要丢弃未推送的改动时才用 `--force`，并在 Jira 评论里写明丢弃了什么。

## 5. 失败原因（写进评论时直接用这套口径）

| `reason` | 含义 | 评论里怎么写 |
|---|---|---|
| `auth-failed` | 令牌缺失或缺少写仓库权限 | 「推送失败（auth-failed）：GitLab 令牌缺少写权限，请补充后重试」 |
| `push-rejected` | 分支受保护或不允许推送 | 「推送被拒绝（push-rejected）：目标分支受保护」 |
| `non-fast-forward` | 远端已有新提交 | 「推送失败（non-fast-forward）：远端分支已更新，需要先合并基线分支」 |
| `network` | 连不上 GitLab | 「推送失败（network）：网络不可达」 |
| `repo-not-found` | 仓库不存在或无权限访问 | 「仓库不存在或无权访问：<仓库地址>」 |
| `base-branch-not-found` | 方案里的基线分支在远端不存在 | 「基线分支 <分支> 不存在，远端现有分支：...」 |
| `repo-needs-base-url` | 方案只给了 `group/repo` 且没配 `GIT_BASE_URL` | 「无法确定 GitLab 地址，需要配置 GIT_BASE_URL」 |
| `unpushed-commits` | 本地还有提交没推到远端 | 「本地还有 N 个提交未推送，已保留检出目录，先补推送」 |
| `uncommitted-changes` | 检出目录里还有未提交的改动 | 「本地还有 N 处未提交改动，已保留检出目录」 |
| `remote-branch-missing` | 远端没有该 feature 分支 | 「远端没有 feature/<KEY>，代码未推成功，保留本地以便排查」 |
| `not-managed-checkout` / `dir-mismatch` / `key-mismatch` | 目录不是本技能拉的，或标记与本次参数不一致 | 「拒绝删除非本技能的目录」 |

## 6. 可选：用 GitLab API 只读核对

需要确认仓库是否存在、基线分支是否还在时，可以用同一令牌调只读接口（脚本不依赖它）：

```bash
curl -s -H "PRIVATE-TOKEN: $GITLAB_PRIVATE_TOKEN" \
  "$GIT_BASE_URL/api/v4/projects/<URL编码的group%2Frepo>/repository/branches?per_page=100"
```

只做核对用，不要用它来改仓库状态（建分支、合并 MR 等一律不在本技能范围内；分支创建由 `git push` 完成）。

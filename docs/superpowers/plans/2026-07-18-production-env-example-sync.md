# Production Environment Example Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前根目录 `.env` 的全部生产配置、真实值和注释原样同步到生产部署示例。

**Architecture:** `.env` 是本次同步的唯一事实来源，`deploy/.env.production.example` 是 Git 跟踪的生产交付副本。根目录 `.env.example` 保持本地开发用途，不参与同步。

**Tech Stack:** PowerShell、Docker Compose、Git

---

### Task 1: 同步生产环境文件

**Files:**
- Source: `.env`
- Modify: `deploy/.env.production.example`

- [ ] **Step 1: 记录同步前字段差异但不输出值**

运行 PowerShell 解析两个文件，只打印缺失或不同的键名：

```powershell
$parse = {
    param($path)
    $map = @{}
    foreach ($line in Get-Content $path) {
        $text = $line.Trim()
        if (-not $text -or $text.StartsWith('#') -or -not $text.Contains('=')) { continue }
        $key, $value = $text.Split('=', 2)
        $map[$key.Trim()] = $value
    }
    $map
}
$source = & $parse '.env'
$target = & $parse 'deploy/.env.production.example'
$source.Keys | Where-Object { -not $target.ContainsKey($_) -or $target[$_] -ne $source[$_] }
```

Expected: 输出当前尚未同步的键名，不输出任何配置值。

- [ ] **Step 2: 原样复制生产配置**

```powershell
Copy-Item -LiteralPath .env -Destination deploy/.env.production.example -Force
```

该步骤保留 `.env` 中的全部中文注释、配置顺序、生产地址、密码和令牌。

- [ ] **Step 3: 验证文件内容完全一致**

```powershell
$sourceHash = (Get-FileHash -Algorithm SHA256 .env).Hash
$targetHash = (Get-FileHash -Algorithm SHA256 deploy/.env.production.example).Hash
if ($sourceHash -ne $targetHash) { throw '生产环境示例与 .env 不一致' }
```

Expected: 退出码为 `0`，命令不输出任何敏感配置值。

### Task 2: 验证生产交付流程

**Files:**
- Verify: `docker-compose.prod.yml`
- Verify: `scripts/package_production_deploy.ps1`

- [ ] **Step 1: 验证生产 Compose 配置**

```powershell
docker compose --env-file deploy/.env.production.example -f docker-compose.prod.yml config --quiet
```

Expected: 退出码为 `0`。

- [ ] **Step 2: 生成生产部署包并验证白名单**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\package_production_deploy.ps1 -Version env-sync-check
```

Expected: ZIP 仅包含 `.env.production.example`、`docker-compose.prod.yml`、`README.md`、`users.example.csv`。

- [ ] **Step 3: 检查 Git 边界**

```powershell
git status --short
git diff --check
```

Expected: `.env` 不在变更列表中，只有生产 example、设计和计划文件进入提交范围。

### Task 3: 提交并合并

**Files:**
- Commit: `deploy/.env.production.example`
- Commit: `docs/superpowers/specs/2026-07-18-production-env-example-sync-design.md`
- Commit: `docs/superpowers/plans/2026-07-18-production-env-example-sync.md`

- [ ] **Step 1: 提交同步结果**

```powershell
git add deploy/.env.production.example docs/superpowers/plans/2026-07-18-production-env-example-sync.md
git commit -m "chore: sync production env example"
```

- [ ] **Step 2: 快进合并到 main**

```powershell
git checkout main
git merge --ff-only codex/sync-production-env-example
```

- [ ] **Step 3: 在合并结果上复验**

```powershell
docker compose --env-file deploy/.env.production.example -f docker-compose.prod.yml config --quiet
git status --short --branch
```

Expected: Compose 配置通过，工作区无未提交改动。

# External Compose Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让外部 MySQL/Redis 成为默认 Compose 模式，并通过 `local-deps` Profile 显式启用本地依赖。

**Architecture:** MySQL、Redis 使用 Compose Profile；迁移服务使用可选健康依赖。合同测试约束 YAML 和文档，Compose 服务列表验证默认与本地两种模式。

**Tech Stack:** Docker Compose v5、YAML、Python unittest、Markdown。

---

### Task 1: 添加失败合同测试

**Files:**
- Modify: `backend/tests/test_compose_contract.py`

- [ ] 添加测试，要求两个 `local-deps` Profile、两个 `required: false`，并要求 README 同时包含默认外部启动与本地 Profile 启动命令。
- [ ] 运行 `backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_compose_contract -v`，确认测试因配置缺失而失败。

### Task 2: 实现 Profile 和可选依赖

**Files:**
- Modify: `docker-compose.yml`

- [ ] 为 `mysql`、`redis` 增加 `profiles: ["local-deps"]`。
- [ ] 为 `migrate.depends_on.mysql` 和 `migrate.depends_on.redis` 增加 `required: false`。
- [ ] 运行 Compose 合同测试并确认通过。

### Task 3: 更新配置示例和使用文档

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

- [ ] 在 `.env.example` 增加 `COMPOSE_MYSQL_HOST`、`COMPOSE_MYSQL_PORT`、`COMPOSE_REDIS_HOST`、`COMPOSE_REDIS_PORT` 的说明。
- [ ] 将本地快速启动命令改为 `docker compose --profile local-deps up -d --build`。
- [ ] 说明外部依赖配置完成后使用普通 `docker compose up -d --build`。

### Task 4: 验证并提交

**Files:**
- Verify: `docker-compose.yml`
- Verify: `.env.example`
- Verify: `README.md`

- [ ] 验证默认服务列表不包含 MySQL、Redis。
- [ ] 验证 `local-deps` Profile 服务列表包含完整服务。
- [ ] 运行 `docker compose config --quiet`、中文注释审计和 `git diff --check`。
- [ ] 使用本地 Profile 实际启动完整服务并检查健康状态。
- [ ] 提交并合并到 `main`。

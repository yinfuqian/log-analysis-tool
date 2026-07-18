# Production Image Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立本地源码构建与生产镜像部署的独立流程，使生产更新无需复制源码或执行 `--build`。

**Architecture:** 本地 Compose 保留构建配置；生产 Compose 独立且只引用镜像。后端 Dockerfile 使用多阶段构建和运行文件白名单，发布脚本负责构建、推送、导出单个版本镜像。

**Tech Stack:** Docker、多阶段 Dockerfile、Docker Compose、PowerShell、Python unittest。

---

### Task 1: 添加生产部署失败合同测试

**Files:**
- Create: `backend/tests/test_production_deployment_contract.py`

- [ ] 检查 `docker-compose.prod.yml` 存在、不包含 `build:`、不定义 MySQL/Redis，并要求后端镜像被迁移、API、Worker 共用。
- [ ] 检查后端 Dockerfile 存在 `AS build`、`AS runtime` 和从构建阶段白名单复制运行文件。
- [ ] 检查 `.dockerignore` 排除 `users.csv`，部署目录和三个发布脚本存在。
- [ ] 运行测试并确认因文件或配置缺失而失败。

### Task 2: 将后端镜像改为多阶段运行镜像

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `backend/.dockerignore`

- [ ] 创建共享基础阶段、构建验证阶段和最终运行阶段。
- [ ] 构建阶段使用 `users.example.csv` 完成应用与 OCR 自检。
- [ ] 最终阶段只复制应用、迁移、启动脚本、运行命令和 OCR 模型缓存。
- [ ] 最终镜像默认读取 `/data/users.csv`，不包含默认用户表。

### Task 3: 创建生产 Compose 和部署目录

**Files:**
- Create: `docker-compose.prod.yml`
- Create: `deploy/.env.production.example`
- Create: `deploy/users.example.csv`
- Create: `deploy/README.md`

- [ ] 生产 Compose 只定义迁移、API、Worker、前端和运行数据卷。
- [ ] 所有业务镜像必须通过 `BACKEND_IMAGE`、`FRONTEND_IMAGE` 指定。
- [ ] 外部 MySQL、Redis 地址和密码从 `.env.production` 注入。
- [ ] 部署文档说明首次部署、单后端更新、单前端更新、完整更新和离线导入命令。

### Task 4: 创建发布脚本

**Files:**
- Create: `scripts/build_release_images.ps1`
- Create: `scripts/export_release_image.ps1`
- Create: `scripts/package_production_deploy.ps1`

- [ ] 构建脚本支持 `all`、`backend`、`frontend` 组件和可选推送。
- [ ] 导出脚本每次导出一个指定镜像并输出 SHA256。
- [ ] 部署打包脚本只压缩生产 Compose、环境示例、用户表示例和部署说明。

### Task 5: 文档与真实验证

**Files:**
- Modify: `README.md`
- Modify: `.gitignore`

- [ ] README 区分本地 `--build` 与生产 `pull + up -d`。
- [ ] 运行合同测试、中文注释审计、Compose 配置检查和 `git diff --check`。
- [ ] 构建后端和前端发布镜像。
- [ ] 检查最终后端镜像不包含测试、`.env`、`users.csv`。
- [ ] 使用 `docker-compose.prod.yml` 和测试环境变量启动迁移、API、Worker、前端并验证健康。
- [ ] 提交并合并到 `main`。

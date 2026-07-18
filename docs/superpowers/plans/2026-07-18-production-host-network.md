# Production Host Network Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让生产四个服务统一使用 host 网络，前端监听宿主机 8080 并代理宿主机 5000，同时保持本地桥接网络可用。

**Architecture:** 前端 Nginx 配置改为启动时渲染的模板，通过 `FRONTEND_LISTEN_PORT` 和 `API_UPSTREAM` 在本地、生产间切换。生产 Compose 使用 host 网络且不声明端口映射，API 健康检查使用更宽裕的超时。

**Tech Stack:** Docker Compose、Nginx、Dockerfile、Python unittest、PowerShell

---

### Task 1: 添加失败合同测试

**Files:**
- Modify: `backend/tests/test_production_deployment_contract.py`

- [ ] **Step 1: 添加 host 网络合同测试**

```python
def test_production_services_use_host_network_without_port_mappings(self):
    source = (PROJECT_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    self.assertEqual(source.count("network_mode: host"), 4)
    self.assertNotIn("ports:", source)
    self.assertIn("timeout: 30s", source)
    self.assertIn("start_period: 120s", source)
```

- [ ] **Step 2: 添加前端双网络配置合同测试**

```python
def test_frontend_image_supports_bridge_and_host_network_upstreams(self):
    template = (PROJECT_ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    dockerfile = (PROJECT_ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    local_compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    prod_compose = (PROJECT_ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")

    self.assertIn("${FRONTEND_LISTEN_PORT}", template)
    self.assertIn("${API_UPSTREAM}", template)
    self.assertIn("/etc/nginx/templates/default.conf.template", dockerfile)
    self.assertIn("API_UPSTREAM: http://api:5000", local_compose)
    self.assertIn("FRONTEND_LISTEN_PORT: 80", local_compose)
    self.assertIn("API_UPSTREAM: http://127.0.0.1:5000", prod_compose)
    self.assertIn("FRONTEND_LISTEN_PORT: 8080", prod_compose)
```

- [ ] **Step 3: 运行测试并确认因功能缺失而失败**

Run:

```powershell
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_production_deployment_contract -v
```

Expected: 新增的两个测试失败，现有测试继续通过。

### Task 2: 让前端镜像支持可配置网络

**Files:**
- Modify: `frontend/nginx.conf`
- Modify: `frontend/Dockerfile`
- Modify: `docker-compose.yml`

- [ ] **Step 1: 将 Nginx 监听和上游改为模板变量**

```nginx
listen ${FRONTEND_LISTEN_PORT};
set $api_upstream ${API_UPSTREAM};
```

保留 `resolver 127.0.0.11`，本地桥接模式仍可延迟解析 `api`；生产上游为 IP，不依赖 Docker DNS。

- [ ] **Step 2: 让官方 Nginx entrypoint 渲染模板**

```dockerfile
ENV FRONTEND_LISTEN_PORT=80 \
    API_UPSTREAM=http://api:5000

COPY nginx.conf /etc/nginx/templates/default.conf.template

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD-SHELL wget -qO- "http://127.0.0.1:${FRONTEND_LISTEN_PORT}/health" || exit 1
```

- [ ] **Step 3: 本地 Compose 显式使用桥接网络参数**

```yaml
environment:
  FRONTEND_LISTEN_PORT: 80
  API_UPSTREAM: http://api:5000
```

- [ ] **Step 4: 运行合同测试并确认前端部分通过**

Run:

```powershell
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_production_deployment_contract.ProductionDeploymentContractTests.test_frontend_image_supports_bridge_and_host_network_upstreams -v
```

Expected: PASS。

### Task 3: 调整生产 Compose 为 host 网络

**Files:**
- Modify: `docker-compose.prod.yml`

- [ ] **Step 1: 为四个服务声明 host 网络**

在 `migrate`、`api`、`worker`、`frontend` 中分别添加：

```yaml
network_mode: host
```

- [ ] **Step 2: 删除生产端口映射并设置前端 host 参数**

```yaml
environment:
  FRONTEND_LISTEN_PORT: 8080
  API_UPSTREAM: http://127.0.0.1:5000
```

生产 Compose 不再包含任何 `ports:`。

- [ ] **Step 3: 放宽 API 健康检查并调整前端检查端口**

```yaml
healthcheck:
  test: ["CMD", "python", "verify_runtime.py", "--runtime"]
  interval: 30s
  timeout: 30s
  retries: 5
  start_period: 120s
```

前端检查使用：

```yaml
test: ["CMD-SHELL", "wget -qO- http://127.0.0.1:$$FRONTEND_LISTEN_PORT/health | grep ok"]
```

- [ ] **Step 4: 运行全部生产部署合同测试**

Run:

```powershell
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_production_deployment_contract -v
```

Expected: 全部 PASS。

### Task 4: 更新生产部署说明

**Files:**
- Modify: `deploy/README.md`
- Modify: `README.md`

- [ ] **Step 1: 说明生产 host 网络端口**

文档必须明确：API 使用宿主机 5000，前端使用宿主机 8080，生产 Compose 的 `ports` 配置无效且已删除。

- [ ] **Step 2: 说明外部依赖地址规则**

文档必须明确：host 网络下 MySQL、Redis 可使用宿主机或远程真实地址，不使用 `mysql`、`redis`、`api` 等 Compose DNS 名称。

### Task 5: 构建和验证新镜像

**Files:**
- Verify: `frontend/Dockerfile`
- Verify: `frontend/nginx.conf`
- Verify: `docker-compose.yml`
- Verify: `docker-compose.prod.yml`

- [ ] **Step 1: 验证两套 Compose 配置**

```powershell
docker compose --env-file .env -f docker-compose.yml config --quiet
docker compose --env-file deploy/.env.production.example -f docker-compose.prod.yml config --quiet
```

- [ ] **Step 2: 运行前端 Lint、测试和构建**

```powershell
Push-Location frontend\app\log-analyze
npm run lint
npm run test:unit -- --runInBand
npm run build
Pop-Location
```

- [ ] **Step 3: 构建版本 2026-07-18-2 镜像**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_release_images.ps1 all -Version 2026-07-18-2
```

- [ ] **Step 4: 验证前端模板两种渲染结果**

```powershell
docker run --rm -e FRONTEND_LISTEN_PORT=80 -e API_UPSTREAM=http://api:5000 fault-analysis/frontend:2026-07-18-2 nginx -T
docker run --rm -e FRONTEND_LISTEN_PORT=8080 -e API_UPSTREAM=http://127.0.0.1:5000 fault-analysis/frontend:2026-07-18-2 nginx -T
```

Expected: 第一份配置监听 80 且上游为 `api:5000`；第二份监听 8080 且上游为 `127.0.0.1:5000`。

- [ ] **Step 5: 标记阿里云镜像**

```powershell
docker tag fault-analysis/backend:2026-07-18-2 registry.cn-hangzhou.aliyuncs.com/k8s-docker-image-yfq/tools:backend-2026-07-18-2
docker tag fault-analysis/frontend:2026-07-18-2 registry.cn-hangzhou.aliyuncs.com/k8s-docker-image-yfq/tools:frontend-2026-07-18-2
```

- [ ] **Step 6: 生成生产部署包**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\package_production_deploy.ps1 -Version 2026-07-18-2
```

### Task 6: 完成验证、提交与合并

**Files:**
- Commit all files listed above except `windows-client/client_build_info.py`

- [ ] **Step 1: 运行最终检查**

```powershell
python scripts\check_source_comments.py
git diff --check
```

- [ ] **Step 2: 检查暂存范围并提交**

```powershell
git add docker-compose.yml docker-compose.prod.yml frontend/Dockerfile frontend/nginx.conf backend/tests/test_production_deployment_contract.py README.md deploy/README.md docs/superpowers/plans/2026-07-18-production-host-network.md
git status --short
git commit -m "feat: support production host network"
```

`windows-client/client_build_info.py` 必须保持未暂存。

- [ ] **Step 3: 快进合并到 main 并复验**

```powershell
git checkout main
git merge --ff-only codex/production-host-network
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_production_deployment_contract -v
docker compose --env-file deploy/.env.production.example -f docker-compose.prod.yml config --quiet
```

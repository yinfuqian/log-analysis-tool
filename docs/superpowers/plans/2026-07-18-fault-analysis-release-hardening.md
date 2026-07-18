# Fault Analysis Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有项目发布为使用 `gpt-5.6-sol` 高强度推理、对外统一命名为“故障分析工具”、具备完整注释与文档、可通过 Docker 全栈构建和健康验证的交付版本。

**Architecture:** 保留现有 API、数据库和兼容性内部标识，在配置层集中模型与品牌信息；新增独立运行时检查模块，让 Docker 构建、容器健康检查和人工排障复用同一套验证逻辑。Compose 默认提供 MySQL、Redis、迁移、API、Worker 和前端完整环境，外部依赖通过环境变量覆盖。

**Tech Stack:** Python 3.10、Flask、Celery、MySQL、Redis、PaddleOCR、OpenAI 兼容 API、Vue 3、Node.js 20、Nginx、Docker Compose、PyInstaller、unittest/Jest。

---

## 文件结构与职责

- `backend/app/config.py`：模型、推理强度、数据库、Redis、OCR 和品牌配置入口。
- `backend/app/ai_options.py`：把统一配置转换成 Chat/Responses 两种 API 请求参数。
- `backend/app/branding.py`：后端用户可见名称与发布标识。
- `backend/app/runtime_checks.py`：构建期和运行期自检，不承载 HTTP 路由。
- `backend/verify_runtime.py`：自检命令行入口。
- `backend/app/health/routes.py`：存活与就绪 HTTP 接口。
- `backend/Dockerfile`：后端可重复构建、依赖检查、应用导入和 OCR 预热。
- `frontend/Dockerfile`、`frontend/nginx.conf`：前端多阶段生产镜像。
- `docker-compose.yml`：完整服务拓扑、健康检查、依赖顺序和持久化卷。
- `frontend/app/log-analyze/src/config/branding.js`：前端统一产品名称。
- `windows-client/client_branding.py`：桌面客户端统一产品名称与构建名称。
- `scripts/check_source_comments.py`：生产源码注释覆盖审计。
- `scripts/clean_generated.ps1`：仅清理工作区内可再生成文件。
- `README.md`：唯一根使用说明；旧 `README` 删除。

---

### Task 1: 统一模型和高强度推理配置

**Files:**
- Create: `backend/app/ai_options.py`
- Modify: `.env.example`
- Modify: `backend/app/config.py`
- Modify: `backend/app/analysis/routes/routes.py`
- Test: `backend/tests/test_async_config.py`
- Test: `backend/tests/test_async_analysis_routes.py`

- [ ] **Step 1: 写配置失败测试**

在 `backend/tests/test_async_config.py` 增加：

```python
def test_default_model_and_reasoning_effort_are_release_defaults(self):
    config = load_config_module({})
    self.assertEqual(config.Config.OPENAI_MODEL, "gpt-5.6-sol")
    self.assertEqual(config.Config.OPENAI_REASONING_EFFORT, "high")
```

在 `backend/tests/test_async_analysis_routes.py` 增加 Chat 和 Responses 参数测试：

```python
def test_chat_request_sends_high_reasoning_effort(self):
    routes, flask_stub, _, _, fake_openai = load_routes_module()
    flask_stub.current_app.config = {
        "OPENAI_KEY": "token",
        "OPENAI_URL": "https://example.invalid/v1",
        "OPENAI_MODEL": "gpt-5.6-sol",
        "OPENAI_API_STYLE": "chat",
        "OPENAI_REASONING_EFFORT": "high",
    }
    routes.call_ai_model("system", "user")
    call = fake_openai.last_instance.chat.completions.calls[0]
    self.assertEqual(call["model"], "gpt-5.6-sol")
    self.assertEqual(call["reasoning_effort"], "high")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```powershell
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_async_config backend.tests.test_async_analysis_routes -v
```

Expected: FAIL，默认模型仍为 `deepseek-chat`，请求中没有推理参数。

- [ ] **Step 3: 实现统一请求参数**

创建 `backend/app/ai_options.py`：

```python
"""构造 OpenAI 兼容接口的统一模型和深度推理参数。"""


def build_ai_request_options(config, api_style):
    """根据 API 风格返回模型及可选的高强度推理参数。"""
    options = {"model": config.get("OPENAI_MODEL", "gpt-5.6-sol")}
    effort = str(config.get("OPENAI_REASONING_EFFORT", "high") or "").strip().lower()
    if not effort:
        return options
    if api_style in ("response", "responses"):
        options["reasoning"] = {"effort": effort}
    else:
        options["reasoning_effort"] = effort
    return options
```

在 `backend/app/config.py` 设置：

```python
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-sol")
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "high")
```

两种 AI 调用均展开 `build_ai_request_options(app.config, api_style)`，不再在多个函数中重复模型默认值。

- [ ] **Step 4: 更新环境变量示例**

```env
OPENAI_MODEL=gpt-5.6-sol
OPENAI_API_STYLE=chat
OPENAI_REASONING_EFFORT=high
```

- [ ] **Step 5: 运行测试确认通过**

Run: Task 1 Step 2 的命令。

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```powershell
git add .env.example backend/app/config.py backend/app/ai_options.py backend/app/analysis/routes/routes.py backend/tests/test_async_config.py backend/tests/test_async_analysis_routes.py
git commit -m "feat: configure high reasoning fault analysis model"
```

---

### Task 2: 统一“故障分析工具”品牌和客户端构建名称

**Files:**
- Create: `backend/app/branding.py`
- Create: `windows-client/client_branding.py`
- Create: `frontend/app/log-analyze/src/config/branding.js`
- Modify: `backend/manage_users.py`
- Modify: `frontend/app/log-analyze/src/App.vue`
- Modify: `frontend/app/log-analyze/src/views/LoginView.vue`
- Modify: `frontend/app/log-analyze/src/components/AnalysisResult.vue`
- Modify: `windows-client/login_window.py`
- Modify: `windows-client/log_analyzer_client.py`
- Modify: `windows-client/build-exe.bat`
- Modify: `windows-client/build-macos.sh`
- Modify: `windows-client/LogAnalyzerClient-macos.spec`
- Test: `windows-client/tests/test_api_client.py`
- Test: `windows-client/tests/test_auth_client.py`
- Test: `frontend/app/log-analyze/tests/unit/branding.spec.js`

- [ ] **Step 1: 写品牌失败测试**

桌面测试断言所有窗口标题包含“故障分析工具”，不包含“日志分析客户端”。前端测试导入 `PRODUCT_NAME` 并断言：

```javascript
import { PRODUCT_NAME } from '@/config/branding'

test('uses fault analysis product name', () => {
  expect(PRODUCT_NAME).toBe('故障分析工具')
})
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
python windows-client\tests\test_api_client.py -v
python windows-client\tests\test_auth_client.py -v
Push-Location frontend\app\log-analyze; npm test -- --runInBand; Pop-Location
```

Expected: 品牌名称和构建名称断言失败。

- [ ] **Step 3: 创建品牌常量并替换用户可见名称**

`frontend/app/log-analyze/src/config/branding.js`：

```javascript
/** 故障分析工具在浏览器页面中的统一品牌配置。 */
export const PRODUCT_NAME = '故障分析工具'
export const PRODUCT_SUBTITLE = '日志、图片、代码与上下游链路综合故障定位'
```

`windows-client/client_branding.py`：

```python
"""桌面客户端统一品牌名称和发布文件名。"""

PRODUCT_NAME = "故障分析工具"
CLIENT_WINDOW_TITLE = f"{PRODUCT_NAME}客户端"
CLIENT_LOGIN_TITLE = f"{PRODUCT_NAME}登录"
CLIENT_EXECUTABLE_NAME = "FaultAnalyzerClient"
```

用户可见字符串改用常量；内部 API 类名和会话键保持兼容。

- [ ] **Step 4: 更新打包名称**

Windows 使用：

```bat
python -m PyInstaller --onefile --windowed --name FaultAnalyzerClient log_analyzer_client.py
```

macOS spec 输出 `FaultAnalyzerClient.app` 和 `FaultAnalyzerClient-macos.zip`。

- [ ] **Step 5: 运行测试确认通过并提交**

Run: Task 2 Step 2。

```powershell
git add backend/manage_users.py frontend/app/log-analyze/src windows-client
git commit -m "feat: rename product to fault analysis tool"
```

---

### Task 3: 补全应用提示语和深度分析状态

**Files:**
- Modify: `windows-client/log_analyzer_client.py`
- Modify: `windows-client/login_window.py`
- Modify: `windows-client/notice_config.json`
- Modify: `frontend/app/log-analyze/src/components/LogUpload.vue`
- Modify: `frontend/app/log-analyze/src/components/AnalysisResult.vue`
- Modify: `frontend/app/log-analyze/src/views/LoginView.vue`
- Modify: `backend/app/analysis/routes/tasks.py`
- Test: `windows-client/tests/test_api_client.py`
- Test: `windows-client/tests/test_auth_client.py`
- Test: `backend/tests/test_analysis_task_progress.py`

- [ ] **Step 1: 写提示语失败测试**

增加静态文本和进度状态断言：

```python
def test_deep_reasoning_progress_explains_expected_wait(self):
    module = load_client_module()
    self.assertIn("正在进行深度故障推理", inspect.getsource(module.LogAnalyzerWindow._handle_task_progress))
    self.assertIn("请耐心等待", inspect.getsource(module.LogAnalyzerWindow._handle_task_progress))
```

后端任务进度必须区分图片识别、代码定位、深度推理和结果整理。

- [ ] **Step 2: 运行测试确认失败**

```powershell
python windows-client\tests\test_api_client.py -v
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_analysis_task_progress -v
```

- [ ] **Step 3: 实现统一提示语**

提示内容覆盖：

- 登录用户不存在、密码错误、禁用和立即下线
- 账号申请必填项、成功和管理员联系方式
- `log_image` 与 `business_image` 选择说明
- 多图逐张分析和重复问题合并说明
- OCR 首次加载和不可用降级说明
- `gpt-5.6-sol` 深度推理等待说明
- Git、数据库、Redis、OCR、AI 和网络失败说明
- 命令执行前风险提醒

- [ ] **Step 4: 运行测试确认通过并提交**

```powershell
git add windows-client backend/app/analysis/routes/tasks.py backend/tests/test_analysis_task_progress.py frontend/app/log-analyze/src
git commit -m "feat: complete fault analysis user guidance"
```

---

### Task 4: 增加统一运行时检查和健康接口

**Files:**
- Create: `backend/app/runtime_checks.py`
- Create: `backend/verify_runtime.py`
- Modify: `backend/app/health/routes.py`
- Modify: `backend/app/__init__.py`
- Test: `backend/tests/test_runtime_checks.py`
- Test: `backend/tests/test_health_routes.py`

- [ ] **Step 1: 写运行时检查失败测试**

```python
def test_build_checks_cover_application_worker_git_and_ocr(self):
    checks = runtime_checks.run_build_checks(ocr_checker=lambda: {"ok": True})
    self.assertEqual(set(checks), {"python", "dependencies", "application", "celery", "git", "ocr"})
    self.assertTrue(all(item["ok"] for item in checks.values()))


def test_readiness_reports_database_failure(self):
    result = runtime_checks.run_readiness_checks(
        database_checker=lambda: (_ for _ in ()).throw(RuntimeError("database unavailable")),
        redis_checker=lambda: None,
        users_checker=lambda: None,
        storage_checker=lambda: None,
    )
    self.assertFalse(result["ready"])
    self.assertIn("database", result["checks"])
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_runtime_checks backend.tests.test_health_routes -v
```

- [ ] **Step 3: 实现检查模块**

`runtime_checks.py` 每个检查返回：

```python
{"ok": True, "message": "应用创建和路由加载成功", "duration_ms": 12}
```

失败时返回中文错误和异常类型，但不包含密码或连接 URI。`verify_runtime.py` 支持 `--build`、`--runtime`、`--ocr`，任一必需检查失败时退出码为 1。

- [ ] **Step 4: 增加健康接口**

- `GET /health/live`：进程存活，不访问外部服务。
- `GET /health/ready`：检查数据库、Redis、用户 CSV 和目录；全部成功返回 200，否则返回 503。

- [ ] **Step 5: 运行测试确认通过并提交**

```powershell
git add backend/app/runtime_checks.py backend/verify_runtime.py backend/app/health backend/app/__init__.py backend/tests/test_runtime_checks.py backend/tests/test_health_routes.py
git commit -m "feat: add full runtime readiness checks"
```

---

### Task 5: 加固后端 Docker 构建并预热 OCR

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `backend/docker-entrypoint.sh`
- Modify: `backend/requirements-ocr.txt`
- Create: `backend/.dockerignore`
- Test: `backend/tests/test_docker_contract.py`

- [ ] **Step 1: 写 Docker 合同失败测试**

```python
def test_backend_dockerfile_runs_all_build_checks(self):
    source = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")
    self.assertIn("python -m pip check", source)
    self.assertIn("python verify_runtime.py --build", source)
    self.assertIn("python verify_runtime.py --ocr", source)
    self.assertIn("HEALTHCHECK", source)
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_docker_contract -v
```

- [ ] **Step 3: 修改 Dockerfile**

关键构建段必须包含：

```dockerfile
ENV PADDLE_PDX_CACHE_HOME=/data/paddle-cache

RUN python -m pip check \
    && python -m compileall -q app.py celery_worker.py app verify_runtime.py \
    && python verify_runtime.py --build \
    && python verify_runtime.py --ocr

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python verify_runtime.py --runtime || exit 1
```

`.dockerignore` 排除 `.env`、虚拟环境、缓存、日志、上传、仓库缓存和测试产物。

- [ ] **Step 4: 验证后端镜像**

```powershell
docker build --progress=plain -t fault-analysis-backend:test backend
docker run --rm fault-analysis-backend:test python verify_runtime.py --build
docker run --rm fault-analysis-backend:test python verify_runtime.py --ocr
```

Expected: 三条命令退出码均为 0，OCR 输出引擎、模型目录和预测完成信息。

- [ ] **Step 5: 提交**

```powershell
git add backend/Dockerfile backend/docker-entrypoint.sh backend/requirements-ocr.txt backend/.dockerignore backend/tests/test_docker_contract.py
git commit -m "build: verify backend and ocr in container image"
```

---

### Task 6: 构建生产前端镜像

**Files:**
- Modify: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`
- Modify: `frontend/entrypoint.sh`
- Create: `frontend/.dockerignore`
- Modify: `frontend/app/log-analyze/vue.config.js`
- Test: `frontend/app/log-analyze/tests/unit/containerConfig.spec.js`

- [ ] **Step 1: 写前端容器配置失败测试**

测试 Dockerfile 包含 Node 20、`npm ci`、单元测试、生产构建和 Nginx 阶段，Nginx 包含 `/health` 与 SPA fallback。

- [ ] **Step 2: 运行测试确认失败**

```powershell
Push-Location frontend\app\log-analyze; npm test -- --runInBand; Pop-Location
```

- [ ] **Step 3: 实现多阶段镜像**

```dockerfile
FROM node:20-bookworm-slim AS build
WORKDIR /workspace
COPY app/log-analyze/package*.json ./
RUN npm ci
COPY app/log-analyze/ ./
RUN npm test -- --runInBand && npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/dist /usr/share/nginx/html
HEALTHCHECK CMD wget -qO- http://127.0.0.1/health || exit 1
```

- [ ] **Step 4: 验证前端镜像并提交**

```powershell
docker build --progress=plain -t fault-analysis-frontend:test frontend
docker run --rm fault-analysis-frontend:test nginx -t
git add frontend
git commit -m "build: add production frontend container"
```

---

### Task 7: 补齐全栈 Compose

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Create: `backend/tests/test_compose_contract.py`

- [ ] **Step 1: 写 Compose 合同失败测试**

```python
def test_compose_contains_complete_service_graph(self):
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    self.assertEqual(
        set(compose["services"]),
        {"mysql", "redis", "migrate", "api", "worker", "frontend"},
    )
```

并断言 MySQL、Redis、API、Worker、前端均有健康检查，迁移依赖健康的 MySQL，API/Worker 依赖迁移成功。

- [ ] **Step 2: 运行测试确认失败**

```powershell
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_compose_contract -v
docker compose config
```

- [ ] **Step 3: 实现完整服务图**

使用 MySQL 8.4、Redis 7.4、后端共享镜像和前端镜像。数据库和 Redis 地址通过以下运行时变量覆盖：

```yaml
environment:
  MYSQL_HOST: ${COMPOSE_MYSQL_HOST:-mysql}
  REDIS_HOST: ${COMPOSE_REDIS_HOST:-redis}
```

持久化卷包括 `mysql-data`、`redis-data`、`ocr-models`、`uploads`、`runtime-logs` 和 `repo-cache`。

- [ ] **Step 4: 启动并验证完整环境**

```powershell
docker compose build --no-cache
docker compose up -d
docker compose ps
docker compose exec api python verify_runtime.py --runtime
docker compose exec worker celery -A celery_worker.celery_app inspect ping
Invoke-WebRequest http://127.0.0.1:${FRONTEND_PORT:-8080}/health
```

Expected: 所有长期服务为 healthy，迁移服务退出码为 0。

- [ ] **Step 5: 提交**

```powershell
git add docker-compose.yml .env.example backend/tests/test_compose_contract.py
git commit -m "build: provide complete fault analysis compose stack"
```

---

### Task 8: 补充生产源码中文注释并建立审计

**Files:**
- Create: `scripts/check_source_comments.py`
- Modify: `backend/**/*.py`（排除 `backend/tests/**`、`backend/migrations/**`、虚拟环境）
- Modify: `frontend/app/log-analyze/src/**/*.js`
- Modify: `frontend/app/log-analyze/src/**/*.vue`
- Modify: `windows-client/*.py`
- Modify: `backend/*.sh`
- Modify: `windows-client/*.bat`
- Test: `backend/tests/test_source_comments.py`

- [ ] **Step 1: 写注释审计失败测试**

`scripts/check_source_comments.py` 使用 AST 检查 Python 模块、类和函数是否有 docstring；对 Vue/JS 检查文件头职责注释，并输出缺失文件和行号。测试运行审计并预期当前仓库失败。

- [ ] **Step 2: 运行审计确认失败**

```powershell
python scripts\check_source_comments.py
```

Expected: 退出码 1，并列出缺少说明的生产源码。

- [ ] **Step 3: 按模块补充注释**

依次处理：

1. 后端入口、配置、扩展和初始化脚本
2. 认证、审计、上传和用户维护
3. 分析、OCR、Git 和上下游模块
4. 日志、产品、模块和关系模型
5. Windows 客户端与登录窗口
6. 前端 API、认证、路由、视图和组件
7. Docker、Compose、Shell 和 Batch

注释解释职责、参数、返回值、异常和关键设计原因，不给简单赋值逐行加注释。

- [ ] **Step 4: 运行审计和现有测试**

```powershell
python scripts\check_source_comments.py
backend\.venv-win\Scripts\python.exe -m unittest discover -s backend\tests -v
python -m unittest discover -s windows-client\tests -v
Push-Location frontend\app\log-analyze; npm test -- --runInBand; Pop-Location
```

Expected: 注释审计和测试全部通过。

- [ ] **Step 5: 提交**

```powershell
git add scripts backend frontend/app/log-analyze/src windows-client
git commit -m "docs: add maintainable source comments"
```

---

### Task 9: 重写 README 和发布文档

**Files:**
- Create: `README.md`
- Delete: `README`
- Modify: `windows-client/README.md`
- Modify: `windows-client/MACOS_BUILD.md`
- Test: `backend/tests/test_readme_contract.py`

- [ ] **Step 1: 写 README 合同失败测试**

测试必须包含“故障分析工具”、Docker 快速启动、模型、深度推理、OCR、账号 CSV、迁移、健康检查、客户端打包和故障排查章节，并断言旧 README 不存在。

- [ ] **Step 2: 运行测试确认失败**

```powershell
backend\.venv-win\Scripts\python.exe -m unittest backend.tests.test_readme_contract -v
```

- [ ] **Step 3: 编写可执行文档**

README 中的快速启动以以下命令为基线：

```powershell
Copy-Item .env.example .env
docker compose build --no-cache
docker compose up -d
docker compose ps
```

明确本地默认、生产必改项、外部数据库/Redis、OCR 离线模型、`gpt-5.6-sol`、高强度推理和客户端远端地址打包规则。

- [ ] **Step 4: 运行文档测试并提交**

```powershell
git add README.md windows-client/README.md windows-client/MACOS_BUILD.md backend/tests/test_readme_contract.py
git rm README
git commit -m "docs: complete fault analysis deployment guide"
```

---

### Task 10: 安全清理可再生成文件

**Files:**
- Create: `scripts/clean_generated.ps1`
- Modify: `.gitignore`
- Test: `backend/tests/test_cleanup_script_contract.py`

- [ ] **Step 1: 写清理合同失败测试**

断言脚本只包含显式允许目录，不调用 `git clean -X`，不匹配 `.env`、`users.csv`、源码、测试和文档。

- [ ] **Step 2: 实现路径安全清理**

脚本先使用 `Resolve-Path` 验证每个目标在工作区内，然后删除：

- `**/__pycache__`
- `.pytest_cache`、`.mypy_cache`
- 前端 `node_modules`、`dist`、临时 build
- Windows 客户端旧 `build`、旧 `dist` 和临时 spec
- 运行日志和临时上传数据
- `frontend/tmp.vue` 等空临时文件

支持 `-DryRun` 和 `-KeepReleaseArtifacts`。

- [ ] **Step 3: 先预览再执行**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\clean_generated.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File scripts\clean_generated.ps1 -KeepReleaseArtifacts
git status --short
```

Expected: `.env`、`users.csv` 和源码仍存在，只清除可再生成内容。

- [ ] **Step 4: 提交**

```powershell
git add .gitignore scripts/clean_generated.ps1 backend/tests/test_cleanup_script_contract.py
git commit -m "chore: safely clean generated workspace files"
```

---

### Task 11: 完整发布验证和客户端打包

**Files:**
- Modify: `windows-client/update_build_info.py`
- Modify: `windows-client/client_build_info.py`
- Generate: `windows-client/dist/FaultAnalyzerClient.exe`
- Create: `docs/release-verification.md`

- [ ] **Step 1: 运行所有静态和单元验证**

```powershell
python scripts\check_source_comments.py
backend\.venv-win\Scripts\python.exe -m unittest discover -s backend\tests -v
python -m unittest discover -s windows-client\tests -v
Push-Location frontend\app\log-analyze; npm ci; npm run lint; npm test -- --runInBand; npm run build; Pop-Location
docker compose config
```

- [ ] **Step 2: 构建并启动完整容器环境**

```powershell
docker compose build --no-cache
docker compose up -d
docker compose ps
docker compose exec api python verify_runtime.py --runtime
docker compose exec api python verify_runtime.py --ocr
docker compose exec worker celery -A celery_worker.celery_app inspect ping
```

- [ ] **Step 3: 执行端到端冒烟验证**

验证：

- `GET /health/live` 返回 200
- `GET /health/ready` 返回 200
- 默认 `admin/admin123` 登录成功
- 日志文件提交并返回结构化问题明细
- 单张日志截图进入多模态分析
- 两张图片均进入请求且图片任务不命中知识缓存
- 禁用用户和立即下线状态生效
- 操作日志记录当前用户

- [ ] **Step 4: 打包桌面客户端**

```powershell
Push-Location windows-client
python update_build_info.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --name FaultAnalyzerClient log_analyzer_client.py
Pop-Location
```

启动 EXE 4 秒确认进程保持运行，再关闭测试进程并记录 SHA256。

- [ ] **Step 5: 记录发布证据**

`docs/release-verification.md` 记录每条命令、退出码、测试数量、镜像 ID、健康状态、客户端版本和 SHA256；失败项必须记录实际原因，不得写“预计通过”。

- [ ] **Step 6: 最终安全清理和提交**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\clean_generated.ps1 -KeepReleaseArtifacts
git add docs/release-verification.md windows-client/client_build_info.py windows-client/update_build_info.py
git commit -m "release: verify fault analysis tool delivery"
```

---

## 最终验收清单

- [ ] `.env.example` 默认模型为 `gpt-5.6-sol`，深度推理为 `high`。
- [ ] Chat 和 Responses 请求均携带正确推理参数。
- [ ] 用户可见位置统一使用“故障分析工具”。
- [ ] `FaultAnalyzerClient.exe` 可启动。
- [ ] 提示语覆盖登录、申请、多图、OCR、深度推理和失败原因。
- [ ] 注释审计通过，复杂生产代码有中文维护说明。
- [ ] README 与实际构建、部署和验证命令一致。
- [ ] 后端和前端镜像构建成功。
- [ ] OCR 在镜像内完成真实初始化和预测。
- [ ] MySQL、Redis、迁移、API、Worker 和前端服务健康。
- [ ] 图片任务不读取或写入日志知识缓存。
- [ ] 两张图片均参与最终分析。
- [ ] 清理脚本没有删除 `.env`、用户 CSV、源码和发布包。


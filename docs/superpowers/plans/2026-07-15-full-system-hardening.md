# 日志分析系统整体加固实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 在暂不改动 Git 安全策略的前提下，为网页端和 Windows 客户端增加强制登录，完成上传与文件路径安全、数据库完整性、事务和查询优化、代码拆分、可重复部署、CI 与中文文档。

**架构：** 后端新增独立 `auth`、`uploads` 和共享服务模块，Flask 在请求入口默认执行鉴权，Redis 保存不设短期过期时间的服务端会话。网页端和 Windows 客户端只在当前应用会话中保存令牌；后端业务 URL 在重构期间保持兼容。数据库、客户端和部署改造按可独立验证的阶段提交。

**技术栈：** Python 3.11、Flask 3、Werkzeug、Redis、Celery、SQLAlchemy/Alembic、Vue 3、Vue Router、Axios、Element Plus、DOMPurify、Tkinter、Docker Compose、GitHub Actions。

---

## 文件结构与实施边界

新增或重点调整的文件职责如下：

- `backend/app/auth/users.py`：用户 JSON 文件解析、校验与原子热加载。
- `backend/app/auth/sessions.py`：Redis 会话创建、校验、注销与登录限流。
- `backend/app/auth/routes.py`：`/auth/login`、`/auth/logout`、`/auth/me`。
- `backend/app/auth/middleware.py`：默认保护业务接口，解析 Bearer Token。
- `backend/app/health/routes.py`：匿名存活检查和需要依赖的就绪检查。
- `backend/manage_users.py`：交互式生成 Werkzeug 密码哈希。
- `backend/app/uploads/validation.py`：上传数量、字节、格式和图片尺寸校验。
- `backend/app/uploads/references.py`：依据 `log_id` 解析受控服务器路径。
- `backend/app/api_errors.py`：统一 JSON 错误结构。
- `backend/app/analysis/services/`：从大型路由中迁出的输入、知识库和 AI 服务。
- `frontend/app/log-analyze/src/auth/session.js`：网页会话令牌状态。
- `frontend/app/log-analyze/src/api/client.js`：唯一 Axios 实例和 401 处理。
- `frontend/app/log-analyze/src/views/LoginView.vue`：网页登录页。
- `windows-client/api_client.py`：可认证 API 客户端。
- `windows-client/login_window.py`：启动登录窗口。
- `windows-client/result_window.py`：从主文件迁出的结果窗口。
- `backend/migrations/versions/d4f6a8b2c901_relationship_integrity.py`：关系约束、软删除字段和旧数据清理。
- `.github/workflows/ci.yml`：后端、客户端、前端、迁移和 Compose 检查。

现有 Git URL、凭证传递和 Git 命令行为不在本计划中修改。路径安全任务只保证临时工作区清理不会越过允许根目录。

实施开始前必须记录当前 `git status --short`。当前工作区已有 OCR、多语言分析和客户端改动，执行者必须在独立工作树中保留这份基线，且后续提交不得意外混入主工作区中无关的用户改动。

### 任务 1：固定运行时和可重复测试基线

**文件：**
- 新建：`backend/requirements-dev.txt`
- 新建：`.python-version`
- 新建：`frontend/app/log-analyze/.nvmrc`
- 修改：`backend/tests/__init__.py`
- 修改：`README`

- [ ] **步骤 1：记录当前验证结果**

运行：

```powershell
python -m compileall -q backend\app backend\tests windows-client
python -m unittest discover -s windows-client\tests
python -m unittest discover -s backend\tests
```

预期：源码编译成功；客户端 75 项测试通过；后端因本机缺少 Flask/OpenCV 不能全绿。将实际失败原因写入本任务执行记录，不能把环境失败当成功。

- [ ] **步骤 2：声明开发测试依赖和运行时**

`backend/requirements-dev.txt` 内容：

```text
-r requirements.txt
-r requirements-ocr.txt
coverage==7.9.2
```

`.python-version` 写入 `3.11.9`，前端 `.nvmrc` 写入 `20.19.4`。README 的开发环境段明确使用这两个版本。

- [ ] **步骤 3：在干净 Python 3.11 环境安装并运行基线**

运行：

```powershell
python -m pip install -r backend\requirements-dev.txt
python -m unittest discover -s backend\tests
python -m unittest discover -s windows-client\tests
```

预期：若真实 OCR 运行库在当前平台不可用，仅允许明确标记的 OCR 集成测试跳过；其余测试通过。

- [ ] **步骤 4：提交基线声明**

```powershell
git add .python-version frontend/app/log-analyze/.nvmrc backend/requirements-dev.txt README
git commit -m "build: define supported development runtimes"
```

### 任务 2：实现用户文件解析、密码哈希和热加载

**文件：**
- 新建：`backend/app/auth/__init__.py`
- 新建：`backend/app/auth/users.py`
- 新建：`backend/manage_users.py`
- 新建：`backend/tests/test_auth_users.py`
- 新建：`backend/config/users.example.json`
- 修改：`backend/app/config.py`
- 修改：`.env.example`

- [ ] **步骤 1：编写失败测试**

在 `backend/tests/test_auth_users.py` 覆盖：有效文件加载、重复用户名拒绝、明文密码拒绝、错误热加载保留旧快照、修改凭证版本后快照更新。

```python
def test_invalid_reload_keeps_last_valid_snapshot(self):
    store = UserStore(self.users_path)
    first = store.get_user("alice")
    self.users_path.write_text("{broken", encoding="utf-8")
    second = store.get_user("alice")
    self.assertEqual(first.credential_version, second.credential_version)
```

- [ ] **步骤 2：运行并确认失败**

运行：

```powershell
python -m unittest backend.tests.test_auth_users -v
```

预期：因 `app.auth.users` 不存在而失败。

- [ ] **步骤 3：实现最小用户存储**

核心接口固定为：

```python
@dataclass(frozen=True)
class UserRecord:
    username: str
    password_hash: str
    enabled: bool
    credential_version: str

class UserStore:
    def __init__(self, path: str): ...
    def get_user(self, username: str) -> UserRecord | None: ...
    def verify_password(self, username: str, password: str) -> UserRecord | None: ...
```

使用 `threading.RLock` 和文件 `stat()` 标识实现先校验、后原子替换。密码使用 `werkzeug.security.check_password_hash`。配置增加：

```python
AUTH_USERS_FILE = os.getenv("AUTH_USERS_FILE", "/data/users.json")
AUTH_LOGIN_MAX_FAILURES = int(os.getenv("AUTH_LOGIN_MAX_FAILURES", "5"))
AUTH_LOGIN_WINDOW_SECONDS = int(os.getenv("AUTH_LOGIN_WINDOW_SECONDS", "300"))
```

`manage_users.py hash-password` 使用 `getpass.getpass()`，调用 `generate_password_hash(password, method="scrypt")`。

- [ ] **步骤 4：运行测试并验证命令**

```powershell
python -m unittest backend.tests.test_auth_users -v
python backend\manage_users.py hash-password
```

预期：用户存储测试通过；交互命令输出以 `scrypt:` 开头的哈希。

- [ ] **步骤 5：提交用户配置功能**

```powershell
git add backend/app/auth backend/manage_users.py backend/tests/test_auth_users.py backend/config/users.example.json backend/app/config.py .env.example
git commit -m "feat: add hot-reloaded user configuration"
```

### 任务 3：实现 Redis 会话、登录限流和鉴权接口

**文件：**
- 新建：`backend/app/auth/sessions.py`
- 新建：`backend/app/auth/routes.py`
- 新建：`backend/app/auth/middleware.py`
- 新建：`backend/app/health/__init__.py`
- 新建：`backend/app/health/routes.py`
- 新建：`backend/tests/test_auth_routes.py`
- 修改：`backend/app/__init__.py`
- 修改：`backend/extensions.py`

- [ ] **步骤 1：编写登录和失效测试**

测试必须覆盖：匿名业务请求返回 401、登录成功、错误密码不暴露用户是否存在、Bearer Token 可访问业务接口、注销立即失效、修改用户文件凭证版本后旧令牌立即失效、OPTIONS 和 `/health/live` 匿名可用。

```python
def test_credential_version_change_invalidates_existing_session(self):
    token = self.login("alice", "secret")
    self.rewrite_user(version="2")
    response = self.client.get("/product/get", headers={"Authorization": f"Bearer {token}"})
    self.assertEqual(response.status_code, 401)
```

- [ ] **步骤 2：运行并确认失败**

```powershell
python -m unittest backend.tests.test_auth_routes -v
```

预期：认证路由和中间件不存在。

- [ ] **步骤 3：实现会话服务和中间件**

会话服务固定接口：

```python
class SessionService:
    def create(self, user: UserRecord) -> str: ...
    def authenticate(self, raw_token: str) -> UserRecord | None: ...
    def revoke(self, raw_token: str) -> None: ...
    def register_failure(self, username: str, source_ip: str) -> bool: ...
```

令牌使用 `secrets.token_urlsafe(32)`；Redis 键使用 `sha256(raw_token)`，值包含用户名和凭证版本，不设置短期 TTL。中间件仅允许 `auth.login`、`health.live`、`health.ready` 和 OPTIONS 匿名访问。

- [ ] **步骤 4：注册 Blueprint 并运行测试**

```powershell
python -m unittest backend.tests.test_auth_routes backend.tests.test_git_routes backend.tests.test_async_analysis_routes -v
```

预期：鉴权测试通过；旧路由测试使用统一登录辅助函数完成适配。仅当 `app.testing is True` 时允许测试配置 `AUTH_TEST_BYPASS=True`，生产配置不得提供鉴权关闭开关。

- [ ] **步骤 5：提交后端登录鉴权**

```powershell
git add backend/app/auth backend/app/health backend/app/__init__.py backend/extensions.py backend/tests
git commit -m "feat: require authenticated backend sessions"
```

### 任务 4：增加网页登录页、会话状态和统一 Axios 客户端

**文件：**
- 新建：`frontend/app/log-analyze/src/auth/session.js`
- 新建：`frontend/app/log-analyze/src/api/client.js`
- 新建：`frontend/app/log-analyze/src/views/LoginView.vue`
- 新建：`frontend/app/log-analyze/src/assets/styles/login.css`
- 新建：`frontend/app/log-analyze/tests/unit/auth.spec.js`
- 修改：`frontend/app/log-analyze/src/router/index.js`
- 修改：`frontend/app/log-analyze/src/App.vue`
- 修改：`frontend/app/log-analyze/src/main.js`
- 修改：`frontend/app/log-analyze/package.json`

- [ ] **步骤 1：配置前端单元测试并写失败测试**

增加 `test:unit` 脚本和 Vue CLI Jest 依赖。测试登录成功后写入 `sessionStorage`、路由守卫重定向、401 清除会话。

```javascript
test('401 clears the application session', async () => {
  session.setToken('token')
  await handleUnauthorized()
  expect(session.getToken()).toBeNull()
})
```

- [ ] **步骤 2：运行并确认失败**

```powershell
npm ci
npm run test:unit -- --runInBand
```

预期：`auth/session` 和统一客户端不存在。

- [ ] **步骤 3：实现网页会话和登录页**

`session.js` 只使用 `sessionStorage`：

```javascript
const KEY = 'log-analyzer-session'
export const getToken = () => sessionStorage.getItem(KEY)
export const setToken = token => sessionStorage.setItem(KEY, token)
export const clearToken = () => sessionStorage.removeItem(KEY)
```

`client.js` 创建唯一 Axios 实例，添加 Bearer Token；响应 401 时清理令牌并跳转 `/login`。登录页调用 `/auth/login`。路由增加 `meta.requiresAuth` 和全局守卫；`App.vue` 在登录页不显示业务侧栏，并在头部增加退出按钮。

- [ ] **步骤 4：迁移 API 模块到统一客户端**

修改 `analysisresult.js`、`logdashbord.js`、`logupload.js`、`module.js` 和 `product.js`，删除每个文件内重复的 `VUE_APP_BASE_URL` 和 Axios 实例，统一：

```javascript
import apiClient from './client'
return apiClient.get('/product/get')
```

- [ ] **步骤 5：运行前端验证并提交**

```powershell
npm run test:unit -- --runInBand
npm run lint
npm run build
git add frontend/app/log-analyze
git commit -m "feat: add authenticated web application shell"
```

预期：单元测试、lint 和生产构建均通过。

### 任务 5：增加 Windows 客户端登录和内存会话

**文件：**
- 新建：`windows-client/api_client.py`
- 新建：`windows-client/login_window.py`
- 新建：`windows-client/tests/test_auth_client.py`
- 修改：`windows-client/log_analyzer_client.py`
- 修改：`windows-client/tests/test_api_client.py`

- [ ] **步骤 1：编写失败测试**

覆盖登录请求、Bearer Header、401 回调、令牌不写磁盘、退出应用调用注销。

```python
def test_authenticated_request_adds_bearer_token(self):
    client = LogAnalyzerApiClient("http://example", session=self.session)
    client.set_token("abc")
    client.get_products()
    self.assertEqual(self.session.headers["Authorization"], "Bearer abc")
```

- [ ] **步骤 2：运行并确认失败**

```powershell
python -m unittest windows-client.tests.test_auth_client -v
```

- [ ] **步骤 3：提取 API 客户端并实现登录窗口**

`api_client.py` 提供 `login`、`logout`、`set_token`、统一 `_request`。401 时清空内存令牌并调用 `on_unauthorized`。`main()` 先隐藏根窗口并打开 `LoginWindow`，只有登录成功才创建 `LogAnalyzerWindow`。

- [ ] **步骤 4：运行客户端完整测试并提交**

```powershell
python -m unittest discover -s windows-client\tests -v
git add windows-client/api_client.py windows-client/login_window.py windows-client/log_analyzer_client.py windows-client/tests
git commit -m "feat: require login in Windows client"
```

### 任务 6：限制日志和图片上传

**文件：**
- 新建：`backend/app/uploads/__init__.py`
- 新建：`backend/app/uploads/validation.py`
- 新建：`backend/tests/test_upload_security.py`
- 修改：`backend/app/config.py`
- 修改：`backend/app/logfile/routes/routes.py`
- 修改：`backend/app/logfile/routes/log_processing.py`
- 修改：`backend/requirements.txt`

- [ ] **步骤 1：编写上传安全失败测试**

覆盖 100 MB 日志上限、10 MB 单图上限、最多 10 图、伪造扩展名、超大像素图片和多图中途失败清理。

```python
def test_rejects_more_than_ten_images(self):
    files = [make_image_file(f"{index}.png") for index in range(11)]
    response = self.client.post("/logfile/upload_image", data={"files": files})
    self.assertEqual(response.status_code, 413)
```

- [ ] **步骤 2：运行并确认失败**

```powershell
python -m unittest backend.tests.test_upload_security -v
```

- [ ] **步骤 3：实现有界验证**

配置增加：

```python
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(120 * 1024 * 1024)))
MAX_LOG_BYTES = int(os.getenv("MAX_LOG_BYTES", str(100 * 1024 * 1024)))
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))
MAX_IMAGE_COUNT = int(os.getenv("MAX_IMAGE_COUNT", "10"))
MAX_IMAGE_PIXELS = int(os.getenv("MAX_IMAGE_PIXELS", "40000000"))
```

使用 Pillow `Image.open()`、`verify()`、格式白名单和 `Image.MAX_IMAGE_PIXELS` 验证图片。读取上传流时使用分块计数，超限立即停止。失败时删除本次已保存文件。

- [ ] **步骤 4：运行上传和 OCR 测试并提交**

```powershell
python -m unittest backend.tests.test_upload_security backend.tests.test_upload_processing_flow backend.tests.test_image_ocr -v
git add backend/app/uploads backend/app/config.py backend/app/logfile backend/requirements.txt backend/tests/test_upload_security.py
git commit -m "feat: enforce bounded validated uploads"
```

### 任务 7：用数据库记录解析分析文件，拒绝任意服务器路径

**文件：**
- 新建：`backend/app/uploads/references.py`
- 新建：`backend/tests/test_analysis_file_references.py`
- 修改：`backend/app/analysis/routes/routes.py`
- 修改：`backend/app/analysis/routes/tasks.py`
- 修改：`windows-client/api_client.py`
- 修改：`windows-client/log_analyzer_client.py`
- 修改：`frontend/app/log-analyze/src/api/logupload.js`

- [ ] **步骤 1：编写路径越权失败测试**

覆盖 `/etc/passwd`、Windows 盘符、上传根目录前缀碰撞、符号链接逃逸、合法 `log_id`、多图片 `log_ids` 和旧字段兼容。

```python
def test_submit_async_rejects_existing_file_outside_upload_root(self):
    response = self.client.post("/analysis/submit_async", json=self.payload(file_path=self.outside_file))
    self.assertEqual(response.status_code, 400)
    self.assertNotIn(str(self.outside_file), response.get_data(as_text=True))
```

- [ ] **步骤 2：运行并确认当前实现失败**

```powershell
python -m unittest backend.tests.test_analysis_file_references -v
```

- [ ] **步骤 3：实现受控引用解析**

核心接口：

```python
def resolve_analysis_inputs(data: dict, upload_root: str) -> list[str]:
    log_ids = data.get("log_ids") or [data.get("log_id")]
    paths = [db.session.get(Log, log_id).log_file_path for log_id in log_ids if log_id]
    return [require_path_under(path, upload_root) for path in paths]
```

旧 `file_path/file_paths` 仅在真实路径位于上传根目录且能匹配 `logs` 表记录时接受。API 错误不得返回服务器绝对路径。上传响应已经提供 `log_id/log_ids`，网页和 Windows 客户端改为提交这些字段。

- [ ] **步骤 4：运行分析、上传和客户端测试并提交**

```powershell
python -m unittest backend.tests.test_analysis_file_references backend.tests.test_async_analysis_routes backend.tests.test_analysis_task_progress -v
python -m unittest discover -s windows-client\tests -v
git add backend/app/uploads/references.py backend/app/analysis backend/tests windows-client frontend/app/log-analyze/src/api
git commit -m "fix: resolve analysis files from trusted records"
```

### 任务 8：修复 Markdown XSS、CORS 和通用安全响应头

**文件：**
- 新建：`backend/tests/test_web_security.py`
- 新建：`frontend/app/log-analyze/tests/unit/markdown.spec.js`
- 修改：`backend/app/__init__.py`
- 修改：`backend/app/config.py`
- 修改：`frontend/app/log-analyze/src/components/MarkdownViewer.vue`
- 修改：`frontend/app/log-analyze/package.json`
- 修改：`.env.example`

- [ ] **步骤 1：编写失败测试**

后端测试 CORS 白名单和响应头；前端测试 `<script>`、事件属性、`javascript:` 链接均被移除。

- [ ] **步骤 2：运行并确认失败**

```powershell
python -m unittest backend.tests.test_web_security -v
npm run test:unit -- --runInBand markdown.spec.js
```

- [ ] **步骤 3：实现安全策略**

`MarkdownIt` 设置 `html: false`，渲染结果通过 DOMPurify：

```javascript
const md = new MarkdownIt({ html: false, linkify: true, typographer: true })
const compiledMarkdown = computed(() => DOMPurify.sanitize(md.render(props.content || ''), {
  USE_PROFILES: { html: true }
}))
```

后端配置 `CORS_ALLOWED_ORIGINS`，按逗号拆分传入 `CORS(app, origins=..., supports_credentials=False)`。`after_request` 增加 `X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy` 和与当前资源兼容的 CSP。

删除 `MarkdownViewer.vue` 中通过 CDN 加载的 GitHub Markdown CSS，改用仓库内本地样式，保证 CSP 不需要放行第三方样式域名。

- [ ] **步骤 4：运行验证并提交**

```powershell
python -m unittest backend.tests.test_web_security backend.tests.test_auth_routes -v
npm run test:unit -- --runInBand
npm run build
git add backend/app backend/tests/test_web_security.py frontend/app/log-analyze .env.example
git commit -m "fix: harden browser content and cross-origin access"
```

### 任务 9：增加关系表外键、唯一约束和旧数据清理迁移

**文件：**
- 新建：`backend/migrations/versions/d4f6a8b2c901_relationship_integrity.py`
- 新建：`backend/tests/test_relationship_migration.py`
- 修改：`backend/app/relasionship/models/model.py`
- 修改：`backend/app/branches/models/model.py`

- [ ] **步骤 1：编写模型和迁移失败测试**

断言关系表外键、组合唯一约束、重复数据清理规则和 `Branch.__repr__` 不访问不存在的 `name`。

- [ ] **步骤 2：运行并确认失败**

```powershell
python -m unittest backend.tests.test_relationship_migration -v
```

- [ ] **步骤 3：实现模型与迁移**

模型约束固定为：

```python
__table_args__ = (UniqueConstraint("product_id", "module_id", name="uq_product_modules_pair"),)
product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
module_id = Column(Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=False)
```

`ModuleBranch` 使用相同模式。迁移先按最小 `id` 保留重复项，再删除引用不存在产品、模块或分支的孤儿关系，最后添加外键、唯一约束和索引。修正 `Branch.__repr__` 为地址和版本。

为 `Product` 和 `Module` 增加 `is_active` 布尔字段，默认 `true`。界面中的删除操作改为停用配置，历史 `QueryRecord` 和 `AnalysisKnowledgeCase` 外键继续指向原记录，从而保留历史分析数据。

- [ ] **步骤 4：执行空库和旧库迁移测试并提交**

```powershell
python -m unittest backend.tests.test_relationship_migration backend.tests.test_analysis_knowledge_base -v
flask --app app.py db upgrade
git add backend/migrations backend/app/relasionship backend/app/branches backend/tests/test_relationship_migration.py
git commit -m "feat: enforce relationship data integrity"
```

### 任务 10：统一产品和模块事务并消除 N+1 查询

**文件：**
- 新建：`backend/app/modules/services.py`
- 新建：`backend/tests/test_module_transactions.py`
- 修改：`backend/app/modules/routes/routes.py`
- 修改：`backend/app/product/routes/routes.py`
- 修改：`backend/app/relasionship/models/model.py`

- [ ] **步骤 1：编写事务和查询数量测试**

测试产品不存在时不产生 Branch/Module 半成品、重复并发新增返回 409、模块列表查询数量不随模块数量线性增长、停用产品或模块后历史分析记录保留、默认列表不返回已停用配置、分页参数受到最大值限制。

- [ ] **步骤 2：运行并确认失败**

```powershell
python -m unittest backend.tests.test_module_transactions -v
```

- [ ] **步骤 3：实现单事务服务**

路由先验证全部输入，再调用：

```python
def create_module_configuration(data):
    with db.session.begin():
        product = db.session.execute(select(Product).where(Product.name == data["product_name"])).scalar_one()
        branch = get_or_create_branch(data["branch_address"], data["tag_version"])
        module = Module(name=data["name"])
        db.session.add(module)
        db.session.flush()
        db.session.add_all([
            ProductModule(product_id=product.id, module_id=module.id),
            ModuleBranch(module_id=module.id, branch_id=branch.id),
        ])
    return module
```

模块列表使用一个 JOIN 查询返回产品、模块和分支数据，并默认过滤 `is_active=False`。产品和模块列表支持 `page`、`page_size`，其中 `page_size` 默认 50、最大 200。将多个中途 `commit()` 删除，只在事务成功后提交。删除接口改为停用记录并清理实时配置关系，不删除历史记录引用的产品和模块行。

- [ ] **步骤 4：运行模块、产品和 Git 同步回归测试并提交**

```powershell
python -m unittest backend.tests.test_module_transactions backend.tests.test_git_routes backend.tests.test_gitlab_sync -v
git add backend/app/modules backend/app/product backend/app/relasionship backend/tests/test_module_transactions.py
git commit -m "refactor: make module configuration transactional"
```

### 任务 11：拆分后端分析服务并统一错误结构

**文件：**
- 新建：`backend/app/api_errors.py`
- 新建：`backend/app/analysis/services/__init__.py`
- 新建：`backend/app/analysis/services/input_service.py`
- 新建：`backend/app/analysis/services/knowledge_service.py`
- 新建：`backend/app/analysis/services/ai_service.py`
- 新建：`backend/tests/test_api_errors.py`
- 修改：`backend/app/analysis/routes/routes.py`
- 修改：`backend/app/analysis/routes/tasks.py`

- [ ] **步骤 1：增加特征测试和错误结构测试**

锁定现有 OCR、多语言解析、知识库命中、AI 错误、任务进度和清理结果；统一错误必须包含 `code`、`message`、`request_id`，参数错误可包含 `fields`。

- [ ] **步骤 2：运行特征测试确保重构前通过**

```powershell
python -m unittest backend.tests.test_async_analysis_routes backend.tests.test_analysis_task_progress backend.tests.test_analysis_knowledge_base backend.tests.test_api_errors -v
```

- [ ] **步骤 3：逐个迁移纯业务单元**

先迁移输入解析，再迁移知识库，最后迁移 AI Provider。`routes.py` 保留同名导入，避免已有测试和调用方立即失效：

```python
from app.analysis.services.ai_service import call_ai_model, call_ai_multimodal_model
from app.analysis.services.knowledge_service import find_knowledge_case, upsert_knowledge_case
```

Celery 任务直接调用服务层，不从路由模块反向导入业务函数。Git 克隆行为保持原样，不在本任务修改安全策略。

- [ ] **步骤 4：运行后端完整测试并提交**

```powershell
python -m unittest discover -s backend\tests -v
git add backend/app/api_errors.py backend/app/analysis backend/tests/test_api_errors.py
git commit -m "refactor: extract analysis application services"
```

### 任务 12：整理前端依赖和 API 模块

**文件：**
- 修改：`frontend/app/log-analyze/package.json`
- 修改：`frontend/app/log-analyze/package-lock.json`
- 修改：`frontend/app/log-analyze/src/api/analysisresult.js`
- 修改：`frontend/app/log-analyze/src/api/logdashbord.js`
- 修改：`frontend/app/log-analyze/src/api/logupload.js`
- 修改：`frontend/app/log-analyze/src/api/module.js`
- 修改：`frontend/app/log-analyze/src/api/product.js`
- 修改：`frontend/app/log-analyze/src/main.js`
- 删除：`frontend/app/log-analyze/src/api/log.js`

- [ ] **步骤 1：增加 API 合约测试**

为产品、模块、上传、任务状态 API 写 Mock Axios 测试，锁定 URL、请求方法和返回数据解包方式。

- [ ] **步骤 2：删除未使用依赖和重复客户端**

删除 `marked`、`vuetify`，保留 `markdown-it`、DOMPurify、Element Plus、Vue Router。所有 API 文件只允许导入 `./client`，禁止直接导入 Axios。

- [ ] **步骤 3：运行依赖、测试、lint 和构建验证**

```powershell
npm ci
npm run test:unit -- --runInBand
npm run lint
npm run build
```

- [ ] **步骤 4：提交前端整理**

```powershell
git add frontend/app/log-analyze
git commit -m "refactor: consolidate frontend API dependencies"
```

### 任务 13：增量拆分 Windows 客户端大型文件

**文件：**
- 新建：`windows-client/result_window.py`
- 新建：`windows-client/dialogs.py`
- 新建：`windows-client/task_polling.py`
- 修改：`windows-client/log_analyzer_client.py`
- 修改：`windows-client/LogAnalyzerClient-macos.spec`
- 修改：`windows-client/tests/test_api_client.py`

- [ ] **步骤 1：为可移动单元增加导入和行为测试**

先锁定 `AnalysisResultWindow`、上下游选择对话框、`poll_analysis_task` 的公开调用方式和静态中文标签。

- [ ] **步骤 2：逐模块移动且每次运行测试**

顺序固定为：结果窗口、对话框、任务轮询。每移动一个单元，主文件通过显式导入保持原调用点：

```python
from result_window import AnalysisResultWindow
from dialogs import RelatedModuleVersionDialog, RelatedEvidenceDialog
from task_polling import poll_analysis_task
```

- [ ] **步骤 3：验证测试和 PyInstaller 分析**

```powershell
python -m unittest discover -s windows-client\tests -v
pyinstaller --noconfirm --clean windows-client\LogAnalyzerClient-macos.spec
```

预期：测试通过，PyInstaller 能找到新模块。若当前 Windows 环境无法产出 macOS 包，至少完成 spec 分析并在 macOS CI 中执行正式构建。

- [ ] **步骤 4：提交客户端拆分**

```powershell
git add windows-client
git commit -m "refactor: split Windows client responsibilities"
```

### 任务 14：统一时间、错误日志和日志轮转

**文件：**
- 修改：`backend/app/__init__.py`
- 修改：`backend/app/config.py`
- 修改：所有使用 `datetime.utcnow()` 的后端业务文件
- 新建：`backend/tests/test_logging_config.py`

- [ ] **步骤 1：编写日志轮转和时区测试**

验证使用 `RotatingFileHandler`、重复 `create_app()` 不重复添加 Handler、业务时间为 UTC aware datetime、Authorization Header 不进入日志。

- [ ] **步骤 2：实现并运行测试**

使用：

```python
from datetime import UTC, datetime
now = datetime.now(UTC)
```

日志配置增加 `LOG_MAX_BYTES` 和 `LOG_BACKUP_COUNT`，默认 20 MB、5 个备份。

运行：

```powershell
python -m unittest backend.tests.test_logging_config -v
python -m unittest discover -s backend\tests -v
```

- [ ] **步骤 3：提交可观测性改造**

```powershell
git add backend/app backend/tests/test_logging_config.py .env.example
git commit -m "refactor: standardize UTC timestamps and log rotation"
```

### 任务 15：改造前后端 Docker 构建

**文件：**
- 修改：`backend/Dockerfile`
- 修改：`frontend/Dockerfile`
- 新建：`frontend/nginx.conf`
- 修改：`frontend/docker-compose.yaml`
- 修改：`docker-compose.yml`
- 删除：`frontend/entrypoint.sh`
- 修改：`.dockerignore` 或新增后端、前端 `.dockerignore`

- [ ] **步骤 1：增加 Compose 静态验证测试**

扩展 `backend/tests/test_runtime_concurrency_config.py`，断言前端不在启动时执行 `npm install`，后端 Dockerfile 创建非 root 用户，API 健康检查改用 `/health/ready`，用户文件以只读方式挂载。

- [ ] **步骤 2：实现多阶段前端镜像**

前端 Dockerfile 使用 Node 20 构建和 Nginx 运行：

```dockerfile
FROM node:20.19.4-alpine AS build
WORKDIR /app
COPY app/log-analyze/package*.json ./
RUN npm ci
COPY app/log-analyze/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
```

- [ ] **步骤 3：后端使用非 root 用户并挂载用户文件**

创建固定 UID 用户，安装依赖后切换 `USER appuser`。Compose 为 API 和 Worker 添加 `./data/users.json:/data/users.json:ro`，健康检查使用匿名健康端点。

- [ ] **步骤 4：验证并提交**

```powershell
docker compose config
docker build -f backend\Dockerfile backend
docker build -f frontend\Dockerfile frontend
python -m unittest backend.tests.test_runtime_concurrency_config -v
git add backend/Dockerfile frontend docker-compose.yml backend/tests/test_runtime_concurrency_config.py
git commit -m "build: make application containers reproducible"
```

### 任务 16：增加 CI、中文部署文档和最终回归

**文件：**
- 新建：`.github/workflows/ci.yml`
- 新建：`docs/authentication.md`
- 新建：`docs/upgrade.md`
- 修改：`README`
- 修改：`.env.example`

- [ ] **步骤 1：实现 CI 工作流**

工作流包含以下独立 job：

```yaml
jobs:
  backend-tests:
  windows-client-tests:
  frontend-tests:
  migration-tests:
  compose-validation:
  secret-scan:
```

后端使用 Python 3.11，前端使用 Node 20；前端执行 `npm ci`、测试、lint、build；迁移 job 启动 MySQL 服务并从空库执行 `flask db upgrade`；Compose job 执行 `docker compose config`；密钥扫描使用 Gitleaks。

- [ ] **步骤 2：编写中文运维文档**

`docs/authentication.md` 给出密码哈希生成、`users.json` 示例、热加载、禁用用户和会话失效说明。`docs/upgrade.md` 给出备份、迁移、回滚边界和 Docker 升级步骤。README 更新启动方式和支持版本，删除“只支持 Java、未做并发测试”等过时描述。

- [ ] **步骤 3：运行最终验证**

```powershell
python -m compileall -q backend\app backend\tests windows-client
python -m unittest discover -s backend\tests -v
python -m unittest discover -s windows-client\tests -v
npm --prefix frontend\app\log-analyze ci
npm --prefix frontend\app\log-analyze run test:unit -- --runInBand
npm --prefix frontend\app\log-analyze run lint
npm --prefix frontend\app\log-analyze run build
docker compose config
git diff --check
```

预期：所有命令退出码为 0；没有跳过非 OCR 环境类核心测试；Git 工作区只包含明确保留的用户改动。

- [ ] **步骤 4：提交 CI 和文档**

```powershell
git add .github docs README .env.example
git commit -m "ci: verify hardened application workflows"
```

## 实施检查点

- 完成任务 3 后：后端已强制登录，但客户端尚未适配，只能通过 API 测试登录。
- 完成任务 5 后：网页端和 Windows 客户端均可正常登录和退出。
- 完成任务 8 后：第一阶段安全加固完成，可进行一次人工验收。
- 完成任务 10 后：数据库完整性和事务优化完成，执行迁移备份检查。
- 完成任务 14 后：代码结构与可观测性改造完成，执行完整回归。
- 完成任务 16 后：Docker、CI 和中文文档完成，进入最终发布验收。

# 故障分析工具

故障分析工具用于综合分析日志、错误截图、业务页面截图、代码仓库和上下游模块信息。系统会先提取结构化错误证据，再使用 `gpt-5.6-sol` 进行高强度深度推理，输出问题明细、可能原因、代码位置、修复建议和相关模块影响。

## 主要能力

- 日志文件、压缩日志和多张图片统一上传分析。
- `log_image` 日志截图通过 PaddleOCR 提取文字，`business_image` 作为业务页面参与多模态分析。
- 多张图片逐张保留，不相互覆盖；最终结果合并重复问题，但保留不同错误明细。
- 结合主模块、相关模块、分支或 Tag 代码进行故障定位。
- `gpt-5.6-sol` 默认启用 `OPENAI_REASONING_EFFORT=high` 深度推理。
- 用户由管理员维护 `users.csv`，应用热加载新增、禁用和立即下线状态。
- 除登录和账号申请外，服务接口必须携带有效登录令牌。
- 用户操作写入数据库审计表，便于按操作人和请求编号追踪。
- Docker Compose 提供数据库迁移、API、Worker、前端和 OCR 运行环境，并可通过 `local-deps` Profile 启动本地 MySQL、Redis。

## 服务架构

| 服务 | 职责 | 默认端口 |
| --- | --- | --- |
| `frontend` | Nginx 静态页面和 `/api` 反向代理 | `8080` |
| `api` | Flask API、认证、上传、Git 和分析任务提交 | `5000` |
| `worker` | Celery 异步深度分析和 OCR 任务 | 无宿主机端口 |
| `migrate` | 创建数据库并执行 `flask db upgrade` | 一次性容器 |
| `mysql` | 业务数据、知识库和用户操作日志 | `3306` |
| `redis` | 登录会话、限流状态、Celery Broker 和结果存储 | `6379` |

## Docker 快速启动

环境要求：Docker Desktop 或 Docker Engine，且支持 Docker Compose v2。

使用本地 MySQL、Redis 的完整开发环境：

```powershell
Copy-Item .env.example .env
docker compose --profile local-deps up -d --build
docker compose ps -a
```

使用外部 MySQL、Redis 时，先填写 `.env` 中的 `COMPOSE_MYSQL_HOST` 和 `COMPOSE_REDIS_HOST`，然后直接启动；此模式不会创建本地数据库容器：

```powershell
docker compose --profile local-deps down
docker compose up -d --build
docker compose ps -a
```

首次生产启动前至少修改 `.env` 中的以下内容：

```env
MYSQL_PASSWORD=请替换
MYSQL_ROOT_PASSWORD=请替换
REDIS_PASSWORD=请替换
OPENAI_KEY=请填写
OPENAI_URL=https://你的兼容接口地址
```

浏览器访问：`http://127.0.0.1:8080`。

停止服务但保留数据：

```powershell
docker compose down
```

仅在明确要删除数据库、Redis、OCR 模型和上传数据时才执行：

```powershell
docker compose down -v
```

## 用户登录与 users.csv

默认示例账号位于根目录 `users.csv`：

```csv
username,password,status
admin,admin123,1
```

生产环境必须修改默认密码。CSV 状态含义：

- `1`：启用。已登录会话持续有效，直到用户退出或会话过期。
- `0`：禁用。禁止新登录，已登录会话按当前会话生命周期处理。
- `2`：立即下线。禁止登录，并使现有会话在下一次接口调用时失效。

文件会按修改时间热加载，不需要重启 API。用户名和明文密码只保存在管理员维护的 CSV 中；数据库不会保存登录密码，操作日志也不会记录密码。Redis 仅保存会话和限流所需状态。

登录与账号申请接口允许匿名调用；其他业务接口必须携带登录后获得的 Bearer Token。匿名用户可以打开前端页面，但不能执行上传、分析、Git 同步等功能。

账号申请当前默认使用 Mock：

```env
ACCOUNT_REQUEST_PROVIDER=mock
```

后续接入第三方接口时配置：

```env
ACCOUNT_REQUEST_PROVIDER=http
ACCOUNT_REQUEST_API_URL=https://example.com/account-request
ACCOUNT_REQUEST_API_TOKEN=请填写
ACCOUNT_REQUEST_API_TIMEOUT=10
```

申请内容包含用户名、密码、申请人姓名，以及服务端自动生成的申请编号和时间。调用失败时客户端直接提示联系管理员，不在本地保存申请记录。

## 模型与深度推理

默认配置：

```env
OPENAI_MODEL=gpt-5.6-sol
OPENAI_API_STYLE=chat
OPENAI_REASONING_EFFORT=high
```

兼容 Chat Completions 的接口使用 `reasoning_effort=high`；兼容 Responses 的接口使用 `reasoning.effort=high`。如第三方服务不支持对应参数，需要由接口提供方实现兼容，或在确认风险后调整推理强度配置。

## PaddleOCR

后端镜像固定安装 Python 3.10、PaddlePaddle、PaddleOCR、OpenCV 和必要的 Linux 原生库。构建镜像时会真实初始化模型并识别一张包含错误文本的测试图片；任何 OCR 初始化或预测失败都会使 Docker 构建失败。

OCR 模型保存在 `ocr-models` 命名卷。首次构建或清空卷后需要下载模型，界面会提示“图片模型加载时间长，请耐心等待”。

验证 OCR：

```powershell
docker compose exec api python verify_runtime.py --ocr
```

当 `LOCAL_OCR_ENABLED=false` 或 OCR 运行失败时，图片仍可进入后续多模态分析，但日志截图的本地文字证据会降级，结果中会明确说明本地图片服务不可用。

## 数据库迁移

启用 `local-deps` Profile 时，Compose 会先等待本地 MySQL 和 Redis 健康；使用外部依赖时，迁移容器直接连接 `.env` 指定的地址并运行：

```powershell
python init_database.py
flask db upgrade
```

手工执行迁移：

```powershell
docker compose run --rm migrate
```

查看当前迁移日志：

```powershell
docker compose logs migrate
```

## 健康检查与运行验证

- `GET /health/live`：仅确认 API 进程存活。
- `GET /health/ready`：检查数据库、Redis、`users.csv` 和运行目录。

```powershell
Invoke-WebRequest http://127.0.0.1:5000/health/live
Invoke-WebRequest http://127.0.0.1:5000/health/ready
Invoke-WebRequest http://127.0.0.1:8080/health
docker compose exec api python verify_runtime.py --runtime
docker compose exec worker celery -A celery_worker.celery_app inspect ping
```

构建期完整自检：

```powershell
docker build --progress=plain -t fault-analysis-backend:test backend
docker run --rm fault-analysis-backend:test python verify_runtime.py --build
docker run --rm fault-analysis-backend:test python verify_runtime.py --ocr
docker build --progress=plain -t fault-analysis-frontend:test frontend
docker run --rm fault-analysis-frontend:test nginx -t
```

## Git 与外部基础设施

GitLab 或 Git 服务配置保存在 `.env`。不要把真实令牌提交到仓库：

```env
GIT_BASE_URL=https://gitlab.example.com/
GIT_USER=
GIT_PASSWORD=
GITLAB_PRIVATE_TOKEN=
```

Compose 默认不启动本地 MySQL 和 Redis。使用外部服务时配置：

```env
COMPOSE_MYSQL_HOST=数据库地址
COMPOSE_MYSQL_PORT=3306
COMPOSE_REDIS_HOST=Redis地址
COMPOSE_REDIS_PORT=6379
```

外部依赖模式直接执行：

```powershell
docker compose up -d --build
```

只有需要本地依赖时才执行：

```powershell
docker compose --profile local-deps up -d --build
```

## Windows 客户端

源码运行：

```powershell
python -m pip install -r windows-client\requirements.txt
python windows-client\log_analyzer_client.py
```

打包前通过环境变量或根目录 `.env` 配置后端地址：

```env
WINDOWS_CLIENT_BACKEND_URL=https://example.com/logapi
```

未配置时，打包客户端默认访问 `http://127.0.0.1:5000`。打包：

```powershell
windows-client\build-exe.bat
```

产物：`windows-client\dist\FaultAnalyzerClient.exe`。

macOS 必须在目标架构的 Mac 上运行 `windows-client/build-macos.sh`，产物为 `FaultAnalyzerClient.app` 和 `FaultAnalyzerClient-macos.zip`。详细说明见 `windows-client/README.md` 和 `windows-client/MACOS_BUILD.md`。

## 本地开发与测试

后端：

```powershell
backend\.venv-win\Scripts\python.exe -m unittest discover -s backend\tests -v
```

Windows 客户端：

```powershell
python -m unittest discover -s windows-client\tests -v
```

前端：

```powershell
Push-Location frontend\app\log-analyze
npm ci
npm run lint
npm run test:unit -- --runInBand
npm run build
Pop-Location
```

源码中文注释审计：

```powershell
python scripts\check_source_comments.py
```

## 安全清理

先预览，再删除可再生成内容：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\clean_generated.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File scripts\clean_generated.ps1 -KeepReleaseArtifacts
```

清理脚本不会删除 `.env`、`users.csv`、源码、测试、文档和保留的最终发布包。

## 故障排查

### 登录密码正确但无法进入

检查 `users.csv` 的表头、编码和状态值，确认 API 能读取挂载文件：

```powershell
docker compose exec api python verify_runtime.py --runtime
docker compose logs api
```

### 迁移提示 MySQL 认证失败

当前依赖已使用 `PyMySQL[rsa]` 支持 MySQL 8 `caching_sha2_password`。确认使用最新后端镜像，并重新执行 `docker compose build api`。

### 图片长时间停在分析中

首次 OCR 模型加载通常较慢。查看 Worker 日志并执行 OCR 自检：

```powershell
docker compose logs -f worker
docker compose exec api python verify_runtime.py --ocr
```

### 多张图片只看到一个问题

确认客户端使用当前版本，并检查每张图片都获得独立上传引用。相同问题会合并展示，不同错误应分别出现在问题明细中。日志截图请选择 `log_image`，普通业务页面请选择 `business_image`。

### 前端可打开但功能不可用

这是未登录状态的预期行为。先登录，再检查浏览器请求是否携带 `Authorization: Bearer ...`，并查看 `/health/ready` 与 API 日志。


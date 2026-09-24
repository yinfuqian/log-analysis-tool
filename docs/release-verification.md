# 发布验证记录

## 基本信息

- 验证日期：2026-07-18（Asia/Shanghai）
- 验证分支：`codex/full-system-hardening`
- 应用名称：故障分析工具
- AI 模型：`gpt-5.6-sol`
- 默认推理强度：`high`

## 自动化测试

| 范围 | 验证命令或方式 | 结果 |
| --- | --- | --- |
| 后端非 OCR 测试 | 使用 `backend/.venv-win/Scripts/python.exe` 按 `test_*.py` 文件隔离运行 | 208 项通过，各模块退出码均为 0 |
| 后端 OCR 测试 | 将 `test_image_ocr.py` 放入最终 API 容器后运行 | 5 项通过，退出码 0 |
| 后端合计 | 非 OCR 本地隔离测试 + Docker OCR 测试 | 213 项通过 |
| Windows 客户端 | `python -m unittest discover -s tests -q` | 99 项通过，退出码 0 |
| Web 前端 | `npm run test:unit -- --runInBand` | 16 项通过，退出码 0 |
| Web 前端代码检查 | `npm run lint` | 无错误，退出码 0 |
| Web 前端生产构建 | `npm run build` | 构建成功，退出码 0 |
| 中文注释审计 | `python scripts/check_source_comments.py` | 通过，退出码 0 |
| Compose 配置 | `docker compose config --quiet` | 通过，退出码 0 |
| Git 差异格式 | `git diff --check` | 通过，退出码 0 |

后端测试必须按文件隔离运行。部分旧测试会临时替换 `app`、`flask` 等模块，若将全部文件放在同一个 Python 进程中执行，会产生模块状态互相污染和 SQLAlchemy 元数据重复注册，并不代表产品代码或运行依赖缺失。

本机后端虚拟环境没有安装 `cv2`，因此 OCR 测试放在最终 Docker 运行环境中执行。最终容器内 5 项 OCR 单元测试和真实 OCR 初始化/预测均通过。

## Docker 镜像与运行状态

- 后端镜像：`jira-automation-backend:final`
- 后端镜像 ID：`sha256:f24a094994f534b46a955f95d43ff08c900de024148eadf61b5e7b6c44303839`
- 前端镜像：`jira-automation-frontend:final`
- 前端镜像 ID：`sha256:247fd674c70338efda43d7c8a9944a548e0218206af439b3157807ecba3d4d13`
- MySQL：健康
- Redis：健康
- API：健康
- Worker：健康，Celery `inspect ping` 返回 `pong`
- 前端：健康，`/health` 返回 HTTP 200 和 `ok`
- 数据库迁移容器：退出码 0
- Windows CRLF 构建上下文验证：镜像默认 ENTRYPOINT 输出 `ENTRYPOINT_OK`，`docker-entrypoint.sh` 的 CRLF 数量为 0

运行时自检确认数据库、Redis、用户 CSV 和运行目录全部可用。PaddleOCR 三个模型从 `/data/paddle-cache` 加载，真实初始化和预测成功，OCR 自检退出码为 0。

## 登录、授权、账号申请与审计

端到端请求均通过 Docker 前端反向代理 `http://127.0.0.1:8080/api` 发起：

| 场景 | HTTP 状态 | 请求编号 | 审计结果 |
| --- | ---: | --- | --- |
| 匿名提交账号申请 | 202 | `REQ-FCA5FB3EFB33547977896F69` | 匿名操作人，目标用户 `release-verify-user` |
| 匿名访问产品接口 | 401 | `REQ-7880C6AB683D5D72B51B4D26` | 匿名操作人，结果失败 |
| `admin/admin123` 登录 | 200 | `REQ-6A05C037D735C8B1824311C2` | 匿名登录动作，目标用户 `admin` |
| 登录后访问产品接口 | 200 | `REQ-27D0BCBF51C5FE01FAC44A42` | 操作人 `admin`，结果成功 |

四个响应中的 `X-Request-ID` 均能在 `user_operation_logs` 中找到相同记录，证明 Gunicorn 真实请求使用独立事务完成审计落库。账号申请使用 Mock 提供方，不写本地申请记录。

## Windows 客户端发布包

- 版本：`v1.1.40`
- 发布日期：`2026-07-18`
- 文件：`windows-client/dist/FaultAnalyzerClient.exe`
- 文件大小：`26,347,371` 字节
- SHA256：`7FFB72B5DEC44BFFDEA8337DC02D51DA107D3E411648F3731ECA0B2397EB857D`
- 启动验证：隐藏启动 6 秒后主进程仍存活，PyInstaller 主/子进程共 2 个；验证结束后仅关闭本次创建的进程，残留进程数为 0
- 默认后端地址：`http://127.0.0.1:5000`

打包远端版本时设置 `WINDOWS_CLIENT_BACKEND_URL`，`update_build_info.py` 会将对应地址写入发布包；未设置时按约定使用本地地址。

## 已知事项

- 本机 Node.js 为 `v24.14.0`，Docker 前端构建固定使用 Node.js 20，因此本机工具链版本不影响最终容器镜像。
- Browserslist 数据提示已过期 17 个月，不影响本次 Lint 和生产构建成功。
- `npm audit` 当前报告 61 项现有 Vue CLI 依赖树问题：低危 13、中危 26、高危 19、严重 3。本次未强制升级主框架依赖，以避免在发布收尾阶段引入不兼容变更。
- 本机 `127.0.0.1:5000` 当前被 WSL 转发进程占用，而 Docker 端口映射由 Docker 后端监听。Docker API 的真实验证因此通过 `8080/api` 反向代理完成；生产发布应配置实际远端 `WINDOWS_CLIENT_BACKEND_URL`。

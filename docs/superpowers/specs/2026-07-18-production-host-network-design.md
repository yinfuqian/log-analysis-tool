# 生产 Host 网络兼容设计

## 目标

让生产部署的迁移、API、Worker 和前端统一使用 Docker host 网络，同时保持同一个前端镜像仍可用于本地 Compose 默认桥接网络。

## 网络架构

- 生产 `migrate`、`api`、`worker`、`frontend` 全部使用 `network_mode: host`。
- host 网络不使用 Compose 端口映射，因此生产 Compose 删除 `ports`。
- API 继续监听宿主机 `0.0.0.0:5000`。
- 前端 Nginx 在生产环境监听宿主机 `8080`，并把 `/api` 请求转发到 `http://127.0.0.1:5000`。
- MySQL 和 Redis 继续使用 `.env.production` 中的真实地址和端口，不依赖 Docker 服务名。

## 前端镜像兼容

前端镜像把静态 Nginx 配置改为官方镜像支持的模板：

- `FRONTEND_LISTEN_PORT` 控制 Nginx 监听端口，镜像默认值为 `80`。
- `API_UPSTREAM` 控制 API 上游，镜像默认值为 `http://api:5000`。
- 本地 `docker-compose.yml` 显式使用 `80` 和 `http://api:5000`，维持桥接网络行为。
- 生产 `docker-compose.prod.yml` 显式使用 `8080` 和 `http://127.0.0.1:5000`，适配 host 网络。

Nginx 的 `/health`、静态资源和前端路由行为保持不变。

## 健康检查

- API 运行时健康检查仍验证数据库、Redis、用户 CSV 和运行目录。
- API `timeout` 从 10 秒提高到 30 秒，`start_period` 从 60 秒提高到 120 秒，避免远程数据库检查约 8 秒时叠加应用初始化导致误判。
- 前端健康检查使用实际监听端口，在本地检查 80，在生产检查 8080。
- `migrate` 成功退出 0 仍属于正常状态；前端继续等待 API 健康后启动。

## 验证

1. 合同测试检查生产四个服务全部使用 host 网络、生产 Compose 不包含端口映射。
2. 合同测试检查 Nginx 模板包含两个环境变量，且本地与生产 Compose 分别传入正确值。
3. `docker compose config` 分别验证本地和生产配置。
4. 构建前端镜像并验证模板生成后的 Nginx 配置：本地监听 80、上游为 `api:5000`；生产监听 8080、上游为 `127.0.0.1:5000`。
5. 后端合同测试、前端单元测试、Lint、构建和 `git diff --check` 全部通过。

## 变更边界

只修改生产 Compose、本地 Compose 的前端环境、前端 Dockerfile/Nginx 模板、部署文档和相关合同测试。当前工作区已有的 `windows-client/client_build_info.py` 修改不属于本需求，不读取、不修改、不暂存。

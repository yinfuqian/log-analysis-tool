# 故障分析工具生产部署说明

生产服务器只需要本目录中的部署文件和已发布镜像，不需要项目源码，也不要执行 `docker compose up --build`。

生产 Compose 统一使用 Docker host 网络：API 直接监听宿主机 `5000`，前端直接监听宿主机 `8080`。host 网络不使用 `ports` 映射；启动前请确认两个端口未被其他进程占用。

MySQL 和 Redis 必须在 `.env.production` 中填写宿主机可访问的真实 IP 或域名。不要填写 `mysql`、`redis`、`api` 等 Compose 服务名，因为 host 网络不提供 Compose DNS 名称解析。前端镜像会把 `/api` 请求代理到宿主机 `127.0.0.1:5000`。

## 首次部署

1. 将 `docker-compose.prod.yml`、`.env.production.example`、`users.example.csv` 和本说明放在同一目录。
2. 将 `.env.production.example` 复制为 `.env.production`，填写镜像地址、MySQL、Redis、模型和第三方接口配置。
3. 将 `users.example.csv` 复制为 `users.csv`，修改默认密码并由管理员持续维护。
4. 登录镜像仓库后拉取并启动：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml pull
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
docker compose --env-file .env.production -f docker-compose.prod.yml ps -a
```

`migrate` 是一次性迁移容器，成功完成后显示为 `Exited (0)` 属于正常状态。`api`、`worker` 和 `frontend` 应保持运行。

浏览器访问 `http://服务器地址:8080`，API 存活检查为 `http://服务器地址:5000/health/live`。

## 只更新后端

发布端构建并推送新的后端镜像后，只修改 `.env.production` 的 `BACKEND_IMAGE`，然后执行：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml pull migrate api worker
docker compose --env-file .env.production -f docker-compose.prod.yml up -d migrate api worker
```

迁移、API 和 Worker 共用同一个后端镜像，更新后端时必须一起更新，前端镜像不会重新下载或重建。

## 只更新前端

只修改 `.env.production` 的 `FRONTEND_IMAGE`，然后执行：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml pull frontend
docker compose --env-file .env.production -f docker-compose.prod.yml up -d frontend
```

## 完整更新

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml pull
docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

## 离线导入镜像

在可访问镜像的机器上使用仓库中的 `scripts/export_release_image.ps1` 分别导出发生变化的镜像，把 `.tar` 和 `.sha256` 文件传到生产服务器。核对摘要后导入：

```bash
sha256sum -c fault-analysis-backend-2026.07.18-1.tar.sha256
docker load -i fault-analysis-backend-2026.07.18-1.tar
```

导入后无需 `--build`，直接执行对应组件的 `up -d` 命令。

## 回滚

将 `.env.production` 中的镜像标签恢复为上一个已验证版本，再执行对应组件的 `up -d`。不要使用 `latest`，否则无法可靠确认当前版本和回滚目标。

## 安全边界

- 生产服务器不保存源码仓库或完整源码包，只保存部署配置、运行数据和镜像。
- 镜像仍包含程序运行所需的应用文件；Docker 镜像不是加密或防反编译手段，镜像仓库权限仍必须严格控制。
- `.env.production`、`users.csv`、上传文件、日志和 OCR 命名卷不进入镜像。
- `users.csv` 支持热加载；修改用户状态不需要重启服务。
- 不执行 `docker compose down -v`，除非明确需要删除上传文件、日志和 OCR 模型数据。

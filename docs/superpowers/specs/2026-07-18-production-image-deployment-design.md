# 生产镜像部署设计

## 目标

本地开发允许从源码构建；生产服务器不保存源码、不执行 Docker 构建，只通过私有仓库或离线镜像包更新已构建镜像。

## 部署边界

- `docker-compose.yml` 保留为本地开发和构建入口。
- 新增 `docker-compose.prod.yml`，只包含 `migrate`、`api`、`worker`、`frontend`，只允许配置 `image:`，不包含 `build:`、本地 MySQL 或本地 Redis。
- 新增 `deploy/` 生产部署包源文件。生产服务器只需要 Compose 文件、`.env.production`、`users.csv`，不需要 `backend/`、`frontend/` 等源码目录。
- 后端镜像仍需包含 Python 运行代码，但采用多阶段构建和白名单复制，最终阶段不包含测试、开发脚本、`.env`、Git 元数据或默认用户文件。
- 前端继续使用现有多阶段构建，最终阶段只包含 Nginx 和编译后的静态文件。

## 更新方式

- 构建机通过发布脚本按组件构建并推送版本镜像。
- 生产服务器修改 `BACKEND_IMAGE` 或 `FRONTEND_IMAGE` 后执行 `pull` 和 `up -d`。
- 后端镜像由迁移、API、Worker 共用；仅后端变化时只更新一个后端镜像。
- 离线环境通过单镜像导出脚本生成 tar，服务器使用 `docker load` 导入后执行 `up -d`。

## 安全要求

- 密码、Token、真实邮件地址和 `users.csv` 不进入镜像。
- 敏感文件必须在构建上下文阶段排除，不能依赖构建后删除，因为旧 Docker 层仍可恢复内容。
- 生产部署文件不得包含源码挂载和本地数据库服务。

## 验证

- 合同测试检查生产 Compose 不含 `build:`、MySQL、Redis 服务。
- 合同测试检查后端 Dockerfile 存在独立运行阶段和白名单复制。
- 真实构建后检查镜像内不存在测试目录、`.env` 和 `users.csv`。
- 使用生产 Compose 配置检查，并通过已构建镜像启动完整应用服务。

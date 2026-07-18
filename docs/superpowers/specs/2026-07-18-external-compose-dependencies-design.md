# Compose 外部依赖模式设计

## 目标

当 `.env` 配置 `COMPOSE_MYSQL_HOST` 和 `COMPOSE_REDIS_HOST` 时，执行普通 `docker compose up -d --build` 只启动迁移、API、Worker 和前端，不创建本地 MySQL、Redis 容器。

## 设计

- `mysql`、`redis` 服务加入 `local-deps` Profile，默认不启用。
- `migrate` 对本地 MySQL、Redis 的 `depends_on` 标记为 `required: false`；Profile 未启用时直接连接 `.env` 指定的外部地址，启用时仍等待本地依赖健康。
- 本地完整环境统一使用 `docker compose --profile local-deps up -d --build`。
- `.env.example` 和 README 明确区分外部依赖与本地依赖两种启动方式。

## 验证

- 默认 `docker compose config --services` 不包含 `mysql`、`redis`。
- 带 `--profile local-deps` 时服务列表包含完整六项服务。
- Compose 配置检查、合同测试和本地 Profile 实际启动均通过。

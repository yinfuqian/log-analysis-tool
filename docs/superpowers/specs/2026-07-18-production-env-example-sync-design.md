# 生产环境配置示例同步设计

## 目标

将根目录 `.env` 作为当前生产配置事实来源，把其中全部配置项及真实值同步到 `deploy/.env.production.example`，使生产部署包自带当前可用配置。

## 文件边界

- `deploy/.env.production.example`：同步当前 `.env` 的全部键、真实值和用途注释，用于生产部署。
- `.env.example`：继续保留为本地开发和源码构建模板，不复制生产真实值。
- `.env`：继续由 Git 忽略，不直接提交。

## 同步规则

1. `deploy/.env.production.example` 的配置键和值必须与当前 `.env` 一致。
2. 按镜像、端口、数据库、Redis、认证、账号申请、Git、模型和 OCR 分组补充中文注释。
3. 生产 Compose 未直接消费但当前 `.env` 已存在的构建或本地 Compose 参数仍保留，避免示例遗漏配置。
4. 不在测试输出、命令日志和最终说明中打印密码、令牌或模型密钥。

## 安全边界

用户已明确选择把真实密码和令牌写入 Git 跟踪的 example。该操作会使敏感值永久进入 Git 历史，并可能随 `git push` 进入远端仓库；后续即使删除文件内容，也需要轮换凭据并清理历史才能消除泄露风险。

## 验证

- 解析 `.env` 与 `deploy/.env.production.example`，验证键集合和值完全一致，但只输出差异键名，不输出值。
- 验证生产 Compose 能使用该文件完成配置解析。
- 验证生产部署 ZIP 包含更新后的 `.env.production.example`。
- 运行 `git diff --check` 并确认根目录 `.env` 未进入暂存区。

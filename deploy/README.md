# 故障分析工具生产部署说明

生产服务器只需要本目录中的部署文件和已发布镜像，不需要项目源码，也不要执行 `docker compose up --build`。

生产 Compose 统一使用 Docker host 网络：API 直接监听宿主机 `5000`，前端直接监听宿主机 `8080`。host 网络不使用 `ports` 映射；启动前请确认两个端口未被其他进程占用。

MySQL 和 Redis 必须在 `.env.production` 中填写宿主机可访问的真实 IP 或域名。不要填写 `mysql`、`redis`、`api` 等 Compose 服务名，因为 host 网络不提供 Compose DNS 名称解析。前端镜像会把 `/api` 请求代理到宿主机 `127.0.0.1:5000`。

## 首次部署

1. 将 `docker-compose.prod.yml`、`.env.production.example`、`users.example.csv` 和本说明放在同一目录。
2. 将 `.env.production.example` 复制为 `.env.production`，填写镜像地址、MySQL、Redis、模型和第三方接口配置。
3. 将 `users.example.csv` 复制为 `config/users.csv`（`./config` 挂载到容器 `/data/`，即容器内 `/data/users.csv`），修改默认密码并由管理员持续维护。
4. 如需使用技能执行接口（`/skill`），把 `skills/` 目录上传到与 Compose 文件同级的位置（容器只读挂载为 `/data/skills`），技能所需的模型参数在 `.env.production` 中配置。
5. 登录镜像仓库后拉取并启动：

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

## 技能执行（/skill 接口）

技能功能需要两项额外条件，未配置时不影响其余业务功能：

1. 后端镜像需为包含 Codex CLI 的版本（`docker compose ... pull` 拉取最新镜像即可）。
2. 将本包的 `skills/` 目录上传到 Compose 文件同级目录，容器会把它**只读**挂载到 `/data/skills`；目录缺失时 `/skill/list` 返回空列表。

镜像内已预装附件解压工具（`bsdtar`、`unzip` 及可用的 7-Zip 系命令）与 Python/Node 依赖，
技能执行过程中不需要联网安装任何软件；如需确认，可在容器内执行 `docker compose ... exec worker sh -c "command -v bsdtar unzip 7z"`。

技能运行参数（模型、中转地址、请求协议、推理强度）由后端以 `codex exec -c ...` 传入，容器内不需要维护 `config.toml`；
Codex 自身的状态库（`state_*.sqlite` 等）写在 `codex-home` 命名卷中，不会落到宿主机目录。需要附加 Codex 配置时用
`CODEX_EXTRA_ARGS` 追加，例如 `CODEX_EXTRA_ARGS=-c model_context_window=128000`。

`.env.production` 是技能运行参数的唯一权威来源，除下面三项外其余技能配置均已内置默认值，可不再改动：

```env
# 【必填】技能使用的 Jira 个人访问令牌
JIRA_TOKEN=请填写
# 【必填】技能访问的 Jira 站点地址，必须与令牌所属站点一致：技能只允许访问这个地址，
# 传入其它站点的需求单链接会被直接拒绝，避免把评论写到别的环境。
JIRA_BASE_URL=https://jira.in.wezhuiyi.com
# 【必填】Codex 使用的模型中转令牌
CODEX_API_KEY=请填写
```

`docker compose --env-file .env.production` 注入的是真实进程环境变量，优先级最高，不会被宿主目录里任何
`.env` 文件覆盖；容器内也没有 `.env` 文件，因此容器里的取值完全由这份文件决定。

需要按环境调整或加固时，再确认这几项（默认值已可直接使用）：

```env
# 外部系统调用 /skill 接口的独立令牌；默认值为本地验证令牌，生产环境必须替换为随机强令牌
SKILL_API_TOKEN=local-dev-token
# jira_url 允许的主机白名单
SKILL_URL_ALLOWED_HOSTS=jira.in.wezhuiyi.com
# Codex 使用的模型与中转地址
CODEX_MODEL=codex/deepseek-flash
CODEX_BASE_URL=https://newapi.in.wezhuiyi.com/v1
# jira-code 拉分支、推送代码用的 GitLab 凭据（令牌需要仓库写权限）与站点地址
GITLAB_PRIVATE_TOKEN=请填写
GIT_BASE_URL=https://code.in.wezhuiyi.com/
# jira-code 热更新用的流水线平台令牌（个人中心签发）；不填时热更新会跳过并在 Jira 评论里说明
DEVOPS_MCP_TOKEN=请填写
# 流水线 MCP server 地址，有默认值，通常不用改
DEVOPS_MCP_URL=https://devops.ks1.wezhuiyi.com/mcp
```

部署后自检：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec worker \
  node /data/skills/jira-gate-1/scripts/jira-cli.mjs selftest
# jira-code 额外自检 GitLab 凭据（只回显来源，不打印令牌）
docker compose --env-file .env.production -f docker-compose.prod.yml exec worker \
  node /data/skills/jira-code/scripts/git-flow.mjs creds
# 配了 DEVOPS_MCP_TOKEN 时确认流水线 MCP 已写进 Codex 配置
docker compose --env-file .env.production -f docker-compose.prod.yml exec worker \
  sh -c 'grep -c pipeline-integration-mcp /data/codex/config.toml'
curl -H "X-API-Token: <SKILL_API_TOKEN>" http://127.0.0.1:5000/skill/list
```

## 安全边界

- 生产服务器不保存源码仓库或完整源码包，只保存部署配置、运行数据和镜像。
- 镜像仍包含程序运行所需的应用文件；Docker 镜像不是加密或防反编译手段，镜像仓库权限仍必须严格控制。
- `.env.production`、`users.csv`、上传文件、日志和 OCR 命名卷不进入镜像。
- `users.csv` 支持热加载；修改用户状态不需要重启服务。
- 不执行 `docker compose down -v`，除非明确需要删除上传文件、日志和 OCR 模型数据。

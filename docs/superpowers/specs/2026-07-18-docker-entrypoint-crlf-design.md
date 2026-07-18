# Docker Entrypoint CRLF 修复设计

## 问题

Windows 当前启用了 `core.autocrlf=true`，`backend/docker-entrypoint.sh` 在工作区中被转换为 CRLF。镜像能够复制文件并设置执行权限，但 Linux 会把首行 `#!/bin/sh\r\n` 的解释器解析为不存在的 `/bin/sh\r`，容器启动时因此返回：

```text
exec /app/docker-entrypoint.sh: no such file or directory
```

## 方案

采用双重保护：

1. 在仓库 `.gitattributes` 中增加 `*.sh text eol=lf`，保证以后检出和提交的 Shell 脚本统一使用 LF。
2. 在后端 Dockerfile 的源码复制步骤之后，使用 `find` 和 `sed` 清除所有 `.sh` 文件行尾的 `\r`，防止非 Git 构建上下文、压缩包或 Windows 工具再次带入 CRLF。
3. 在 Docker 合同测试中同时检查仓库 LF 规则和镜像构建期转换命令，防止后续回归。

## 验证

- 新增合同测试必须在修改前失败、修改后通过。
- 重新构建后端镜像。
- 使用默认 ENTRYPOINT 启动容器并执行简单命令，确认不再出现 `no such file or directory`。
- 在镜像内部检查 `/app/docker-entrypoint.sh` 不包含 CRLF。
- 运行 Docker 合同测试、运行时自检和 Compose 健康检查。

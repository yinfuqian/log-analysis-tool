# 后端镜像离线 apt 依赖

`backend/Dockerfile` 在构建阶段用 apt 安装运行所需系统依赖（`git`、`ca-certificates`、`curl`、`libgomp1`、
`libgl1`、`libglib2.0-0`、`unzip`、`libarchive-tools`、`p7zip-full`、`7zip`）。本目录保存这些软件包及其
递归依赖的离线 deb 包，用于企业内网等无法访问 apt 源的构建环境。

## 目录结构

- `bookworm-amd64/`：Debian bookworm / amd64 的离线 deb 包。
  - `*.deb`：apt 下载的软件包，文件名中的 `%3a` 是 apt 对版本号中 `:` 的转义，dpkg 可直接安装。
  - `MANIFEST.tsv`：软件包、版本、架构清单。
  - `SHA256SUMS`：deb 包校验和。

## 构建时如何使用

Dockerfile 的 apt 步骤通过 `--mount=type=bind,source=offline/apt` 读取本目录，并按容器内的
`<发行版代号>-<架构>` 匹配子目录：

- 命中（例如 `bookworm-amd64`）：直接 `dpkg -i` 本地 deb 包，完全不访问 apt 源。
- 未命中：回退到 `${APT_MIRROR}` 在线安装，行为与未引入离线包时一致。

因此构建时不需要额外参数，离线构建只需保证构建机已有所需基础镜像（`PYTHON_BASE_IMAGE`）。
该挂载是构建期临时挂载，deb 包不会进入最终镜像。

## 重新导出

系统依赖清单发生变化（修改 `backend/Dockerfile` 的 `ARG APT_PACKAGES`）后必须重新导出：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\export_apt_offline_packages.ps1
```

脚本使用与 Dockerfile 一致的基础镜像，在容器内执行 `apt-get install --download-only` 下载完整依赖树，
写入 `MANIFEST.tsv` 与 `SHA256SUMS`，最后在 `--network none` 的容器里做断网安装自检，并校验
`git`、`curl`、`bsdtar`、`unzip` 与 7-Zip 系命令可用。

可选参数：

```powershell
# 换 apt 源
-AptMirror http://mirrors.aliyun.com/debian
# 换基础镜像或发行版代号
-BaseImage docker.m.daocloud.io/library/python:3.10-slim-bookworm -DebianRelease bookworm
# ARM 服务器（需要构建机支持该架构模拟）
-Architecture arm64
# 只下载不做断网自检
-SkipVerify
```

## 注意事项

- `ARG APT_PACKAGES` 是唯一的依赖来源，离线包必须覆盖该清单；构建结束前的 `dpkg-query` 校验会在缺少包时直接失败。
- 本目录只覆盖 apt 系统依赖，`pip` 依赖（`requirements*.txt`）与 `npm`/Codex CLI 仍需可访问的
  `PIP_INDEX_URL`、`NPM_REGISTRY`。
- deb 包合计约 70 MB，提交进仓库前请确认仓库体积可接受。

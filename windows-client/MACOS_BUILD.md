# macOS 构建说明

`FaultAnalyzerClient.app` 必须在目标 Mac 架构上构建。Intel 与 Apple Silicon 使用不同的原生依赖，不能在 Windows 上交叉生成可运行的 `.app`。

## 推荐环境

- Python 3.10 或 3.11。
- 当前架构为 Intel `x86_64` 或 Apple Silicon `arm64`。
- 可访问配置的 Python 包镜像。

## 配置后端地址

构建前设置：

```bash
export WINDOWS_CLIENT_BACKEND_URL=https://example.com/logapi
```

未设置时默认使用 `http://127.0.0.1:5000`。

## 构建

```bash
cd windows-client
chmod +x build-macos.sh
./build-macos.sh
```

脚本会创建或复用 `.venv-macos`，安装依赖，更新版本信息并执行 PyInstaller。

输出：

```text
windows-client/dist/FaultAnalyzerClient.app
windows-client/dist/FaultAnalyzerClient-macos.zip
```

## 包镜像

```bash
export PIP_INDEX_URL=https://pypi.org/simple
export PIP_TRUSTED_HOST=pypi.org
./build-macos.sh
```

企业内网可以把 `PIP_INDEX_URL` 替换为内部镜像地址。

## 首次打开

若 macOS 提示隔离或安全限制，可在“系统设置 > 隐私与安全性”中允许打开，或对本地可信产物执行：

```bash
xattr -dr com.apple.quarantine dist/FaultAnalyzerClient.app
```

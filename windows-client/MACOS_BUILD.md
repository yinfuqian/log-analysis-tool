# macOS 构建说明

`FaultAnalyzerClient.app` 必须在 macOS 上构建，不能在 Windows 或 Linux 上交叉生成可运行的 `.app`。默认构建结果为 Universal 2，能够同时运行在 Intel `x86_64` 和 Apple Silicon `arm64` Mac 上。

## 一键构建

```bash
cd windows-client
chmod +x build-macos.sh
./build-macos.sh
```

脚本必须保持 Unix LF 行尾。如果出现 `env: bash\r: No such file or directory`，说明使用的是经过 Windows CRLF 转换的旧文件，请重新获取仓库中的最新版 `build-macos.sh`，不要继续使用旧副本。

脚本会自动完成：

1. 检查 macOS 构建工具。
2. 查找符合目标架构的 Python。
3. 缺少 Universal 2 Python 时，从 python.org 下载并安装官方 Python。
4. 创建独立虚拟环境。
5. 下载 `requirements.txt` 中的全部依赖和 PyInstaller。
6. 写入版本、构建日期和后端地址。
7. 执行 PyInstaller、应用签名和 Mach-O 架构验证。
8. 生成可以传输的 ZIP 包。

安装系统 Python 时会通过 `sudo` 请求当前 Mac 的管理员密码。

## 构建架构

默认生成 Universal 2：

```bash
./build-macos.sh
# 等价于
./build-macos.sh universal2
```

只生成 Apple Silicon 版本：

```bash
./build-macos.sh arm64
```

只生成 Intel 版本：

```bash
./build-macos.sh x86_64
```

不同目标使用不同虚拟环境：

```text
.venv-macos-universal2
.venv-macos-arm64
.venv-macos-x86_64
```

## Python 自动安装

默认安装 python.org 发布的 Python 3.11 Universal 2。需要使用其他补丁版本时，可以覆盖：

```bash
export MACOS_PYTHON_VERSION=3.11.9
./build-macos.sh
```

脚本只从以下官方 HTTPS 地址下载：

```text
https://www.python.org/ftp/python/
```

如果已经安装了符合要求的 Python，可以指定路径：

```bash
export MACOS_PYTHON=/Library/Frameworks/Python.framework/Versions/3.11/bin/python3
./build-macos.sh
```

## macOS 系统工具

脚本需要 `curl`、`lipo`、`ditto` 和 `codesign`。如果提示系统构建工具缺失，先执行：

```bash
xcode-select --install
```

等待 macOS 完成安装后重新执行打包脚本。

## 后端地址

macOS 客户端生产后端地址固定在 `build-macos.sh` 中，运行脚本时不需要手动 `export`：

```text
http://qwbot30.wezhuiyi.com:9595/zhuiyi/logapi
```

构建脚本会把该地址写入客户端构建信息并随应用发布。

## Python 包镜像

默认使用当前 `pip` 配置。需要指定官方源或企业内部镜像时：

```bash
export PIP_INDEX_URL=https://pypi.org/simple
./build-macos.sh
```

企业内网可以把 `PIP_INDEX_URL` 替换为内部可信镜像地址。

## 应用签名

没有配置证书时，脚本使用 macOS 临时签名，适合内部测试：

```bash
./build-macos.sh
```

存在 Apple Developer ID 时设置签名身份：

```bash
export MACOS_CODESIGN_IDENTITY="Developer ID Application: Example Company (TEAMID)"
./build-macos.sh
```

脚本会在打包后执行 `codesign --verify`。临时签名不能代替 Apple 公证；向企业外部正式分发时，还需要使用 Apple notarization 流程。

## 构建产物

Universal 2 默认输出：

```text
windows-client/dist/FaultAnalyzerClient.app
windows-client/dist/FaultAnalyzerClient-macos-universal2.zip
```

单架构 ZIP 文件会带有对应架构名称：

```text
windows-client/dist/FaultAnalyzerClient-macos-arm64.zip
windows-client/dist/FaultAnalyzerClient-macos-x86_64.zip
```

脚本会使用 `lipo -archs` 检查应用主程序。Universal 2 产物必须同时包含 `arm64` 和 `x86_64`，否则构建直接失败，不会输出成功提示。

## 首次打开

若内部测试包被 macOS 隔离，可在“系统设置 > 隐私与安全性”中确认允许打开。仅对来源可信的本地产物，也可以执行：

```bash
xattr -dr com.apple.quarantine dist/FaultAnalyzerClient.app
```

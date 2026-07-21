# macOS Universal 2 客户端打包设计

## 目标

完善 `windows-client/build-macos.sh`，默认生成同时支持 Apple Silicon 与 Intel Mac 的 Universal 2 客户端，并允许开发人员按需构建单架构版本。

产物包括：

- `windows-client/dist/FaultAnalyzerClient.app`
- `windows-client/dist/FaultAnalyzerClient-macos-universal2.zip`

## 构建模式

脚本接受一个可选架构参数：

- 不传参数或传入 `universal2`：构建同时包含 `arm64` 和 `x86_64` 的应用。
- 传入 `arm64`：只构建 Apple Silicon 应用。
- 传入 `x86_64`：只构建 Intel 应用。

Universal 2 构建必须使用本身包含 `arm64` 和 `x86_64` 架构的 Python。脚本不尝试用单架构 Python 交叉生成另一种架构，以免产生能够打包但无法运行的客户端。如果本机没有符合要求的 Python，脚本自动下载并安装官方 Universal 2 Python。

## Python 自动安装

脚本优先查找已经安装且架构符合要求的 Python。当没有可用 Python 时：

1. 使用 macOS 自带的 `curl` 从 python.org 下载固定版本的官方 Universal 2 `.pkg` 安装包。
2. 下载过程启用失败重试，并在 HTTP 或 TLS 校验失败时立即停止。
3. 使用 macOS `installer` 安装到系统标准位置；该步骤通过 `sudo` 请求管理员授权。
4. 安装完成后重新定位 Python，并再次验证版本和 Mach-O 架构。
5. 验证通过后才创建项目虚拟环境，不能继续使用原来的单架构 Python。
6. 使用退出陷阱删除下载到临时目录的安装包。

默认 Python 版本固定在脚本中，并允许通过 `MACOS_PYTHON_VERSION` 覆盖，方便后续安全升级。下载地址只允许使用 python.org 官方 HTTPS 域名，不接受第三方镜像或未加密地址。

## 环境检查

脚本启动后依次检查：

1. 当前操作系统必须是 macOS。
2. `curl`、`lipo`、`ditto` 和 `codesign` 必须可用。
3. 自动定位或安装 Python。
4. Python 版本及可执行文件架构满足目标构建模式。
5. Universal 2 模式下，Python 可执行文件必须同时包含 `arm64` 和 `x86_64`。

检查失败时输出中文原因和处理建议。Universal 2 Python 使用 python.org 发布的 Python 3.11 官方安装包。系统工具缺失时脚本给出 Xcode Command Line Tools 安装提示；由于该安装由 macOS 图形界面和系统更新机制控制，不在脚本中模拟或绕过系统授权。

## 构建流程

脚本使用与目标架构对应的虚拟环境，例如 `.venv-macos-universal2`，避免不同架构的依赖相互污染。

构建步骤如下：

1. 定位符合目标架构的 Python；不存在时自动下载安装。
2. 创建或复用目标架构虚拟环境。
3. 更新 `pip`、`setuptools` 和 `wheel`。
4. 自动安装客户端依赖与 PyInstaller，缺失依赖不要求用户手动处理。
5. 备份 `client_build_info.py`。
6. 执行 `update_build_info.py`，把版本、构建日期和 `WINDOWS_CLIENT_BACKEND_URL` 写入应用。
7. 清理旧的 PyInstaller 临时目录和同名产物。
8. 按目标架构运行 PyInstaller。
9. 验证 `.app` 主程序的 Mach-O 架构。
10. 对应用执行签名。
11. 使用 `ditto` 生成 ZIP 包。
12. 恢复构建前的 `client_build_info.py`。

无论成功、失败或用户中断，恢复逻辑都通过退出陷阱执行，避免构建信息残留到源码工作区。

## PyInstaller 配置

`LogAnalyzerClient-macos.spec` 从环境变量读取目标架构，并将其传给 PyInstaller 的 `EXE` 配置。默认目标为 `universal2`。

继续打包：

- `log_analyzer_client.py`
- `notice_config.json`
- 登录窗口、API 客户端及项目内 Python 模块

macOS 不加载 Windows 专用的 `windnd`。

## 签名

脚本支持环境变量 `MACOS_CODESIGN_IDENTITY`：

- 已配置 Apple Developer ID 时，使用指定身份签名。
- 未配置时使用临时签名 `-`，方便内部测试。

临时签名不能替代 Apple 公证。需要向企业外部分发时，应另外执行 Developer ID 签名和 notarization。

## 产物验证

构建完成后必须检查：

- `.app` 目录存在。
- 应用主程序存在且为 Mach-O 文件。
- Universal 2 模式下，主程序同时包含 `arm64` 和 `x86_64`。
- 单架构模式下，主程序包含请求的目标架构。
- ZIP 包能够成功生成。

任一检查失败都应使脚本以非零状态退出，不能提示构建成功。

## 测试和文档

增加不依赖 macOS 的脚本合同测试，静态验证：

- 支持三种架构参数。
- Universal 2 为默认值。
- 缺少 Universal 2 Python 时从 python.org 自动下载安装。
- Python 安装后必须重新执行版本和架构验证。
- Python 包依赖与 PyInstaller 自动下载安装。
- 存在 Python 架构检查。
- 存在产物架构验证。
- 存在退出时恢复构建信息的逻辑。
- 存在签名和 ZIP 打包步骤。

同步更新 `windows-client/README.md` 和 `windows-client/MACOS_BUILD.md`，说明 Universal 2 Python、执行命令、后端地址配置、签名方式和最终产物。

## 范围边界

本次只完善 macOS 客户端构建流程，不修改后端接口、客户端业务功能、登录逻辑和 Windows 打包流程，也不在 Windows 环境假装执行真实的 macOS 二进制构建。

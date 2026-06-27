# 日
志分析桌面客户端

这是一个独立的桌面客户端，通过远程 HTTP 调用后端接口，不需要和后端部署在同一台机器。

当前支持：

- Windows：生成 `LogAnalyzerClient.exe`
- macOS：生成 `LogAnalyzerClient.app`

## 默认后端地址

客户端默认后端地址固定为：

```text
http://qwbot30.wezhuiyi.com:9595/zhuiyi/logapi
```

不要使用 `localhost`，除非你是在本机专门调试后端服务。

## Windows 启动方式

双击运行：

```text
windows-client\start-log-analyzer.bat
```

或者命令行运行：

```powershell
python windows-client\log_analyzer_client.py
```

## 打包 Windows exe

先安装依赖：

```powershell
python -m pip install -r windows-client\requirements.txt
```

然后打包：

```powershell
windows-client\build-exe.bat
```

说明：每次执行 `build-exe.bat` 会自动递增客户端补丁版本，并把打包日期刷新为当天；如果打包失败，会自动恢复旧版本号。

打包成功后会生成：

```text
windows-client\dist\LogAnalyzerClient.exe
```

## macOS 启动方式

源码方式运行：

```bash
cd windows-client
python3 -m pip install -r requirements.txt
python3 log_analyzer_client.py
```

## 打包 macOS App

macOS 应用需要在 Mac 机器上打包，不能在 Windows 上直接交叉生成可运行的 `.app`。

在 Mac 上执行：

```bash
cd windows-client
chmod +x build-macos.sh
./build-macos.sh
```

说明：每次执行 `build-macos.sh` 会自动递增客户端补丁版本，并同步写入 macOS App 的 Bundle 版本；如果打包失败，会自动恢复旧版本号。

打包成功后会生成：

```text
windows-client/dist/LogAnalyzerClient.app
windows-client/dist/LogAnalyzerClient-macos.zip
```

## 依赖说明

- 当前客户端必备依赖：`requests`、`Pillow`、`PyInstaller`。
- 图片模式支持选择图片文件、粘贴图片，也支持多张图片暂存后统一上传。
- Windows 拖拽图片依赖额外的 `windnd` 扩展；macOS 版本不包含该扩展，不影响选择文件、粘贴图片、上传和分析。
- macOS 首次打开如果提示安全限制，可以在“系统设置 > 隐私与安全性”里允许打开，或执行 `xattr -dr com.apple.quarantine dist/LogAnalyzerClient.app` 解除本地隔离标记。

## 公告配置

公告内容来自 `windows-client\notice_config.json`，可以直接修改：

```json
{
  "title": "{app_release_label}",
  "lines": [
    "使用方法：...",
    "适用范围：...",
    "使用场景：...",
    "后端地址：{backend_url}",
    "故障联系人：尹甫乾&张尧",
    "隐私性说明：..."
  ]
}
```

支持的占位符：

- `{app_release_label}`：客户端版本和发版日期，例如 `日志分析客户端/v1.1.7 fix on 2026-06-27`。
- `{app_version}`：客户端版本，例如 `v1.1.7`。
- `{app_release_date}`：发版日期。
- `{backend_url}`：默认后端地址。

打包后如果需要临时改公告，可以把新的 `notice_config.json` 放到 `LogAnalyzerClient.exe` 同目录；客户端启动时会优先读取外部配置。

## 使用流程

1. 后端地址默认已经填好：`http://qwbot30.wezhuiyi.com:9595/zhuiyi/logapi`。
2. 点击“同步 Git 项目”，客户端会调用后端同步产品、模块、分支和 Tag 信息。
3. 产品、模块、分支地址、版本/Tag、日期条件下拉框都支持输入关键字检索。
4. 选择产品后，客户端会自动加载该产品关联的模块、分支地址和版本/Tag。
5. 输入方式支持两种：
   - `日志文件`：选择 `.log`、`.txt` 或 `.gz` 文件。
   - `图片识别`：支持选择图片文件或粘贴图片，并选择 `log_image` / `business_image` 标签。
6. 日期条件可以留空读取全量，也可以填写 `-3`，或填写 `2026-06-07` 这类绝对日期。
7. 点击“上传日志”或“上传图片”，再点击“开始分析”。分析完成后，结果会在主窗口和详情弹窗中展示。

## 接口说明

客户端主要调用这些远程接口：

- `/product/get`
- `/module/get?product_id=...`
- `/git/sync-projects`
- `/git/branches?repo_url=...`
- `/logfile/upload`
- `/logfile/upload_image`
- `/analysis/submit_async`
- `/analysis/task/<task_id>`
- `/analysis/task/<task_id>/cancel`

后端需要能被当前桌面机器访问，并且后端配置中的数据库、Git 和模型 API 能正常使用。

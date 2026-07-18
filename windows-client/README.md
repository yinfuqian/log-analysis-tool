# 故障分析工具桌面客户端

桌面客户端通过 HTTP 调用故障分析工具后端，支持登录、账号申请、日志上传、图片上传、多模块代码关联和异步深度分析。

## 后端地址

源码运行时，若没有生成构建信息，默认地址为：

```text
http://127.0.0.1:5000
```

打包前可在进程环境变量或项目根目录 `.env` 中配置：

```env
WINDOWS_CLIENT_BACKEND_URL=https://example.com/logapi
```

`update_build_info.py` 会把该地址写入 `client_build_info.py`，随客户端一起打包。不同环境应使用不同配置重新打包，不需要在源码中硬编码地址。

## 登录与账号申请

客户端启动后先显示登录窗口。用户名和密码由管理员维护后端 `users.csv`；密码错误、账号禁用和立即下线都会显示明确提示。

登录窗口的“申请账号”会统一调用后端账号申请接口，填写用户名、密码和申请人姓名。后端当前可使用 Mock，后续可切换为第三方 HTTP 接口。

## Windows 源码运行

```powershell
python -m pip install -r windows-client\requirements.txt
python windows-client\log_analyzer_client.py
```

也可以双击：

```text
windows-client\start-log-analyzer.bat
```

## Windows 打包

```powershell
windows-client\build-exe.bat
```

构建脚本会更新版本和构建日期；失败时恢复原版本信息。产物：

```text
windows-client\dist\FaultAnalyzerClient.exe
```

## macOS 打包

macOS 应用必须在目标 Mac 架构上构建：

```bash
cd windows-client
chmod +x build-macos.sh
./build-macos.sh
```

产物：

```text
windows-client/dist/FaultAnalyzerClient.app
windows-client/dist/FaultAnalyzerClient-macos.zip
```

## 图片分析说明

- 日志或错误截图选择 `log_image`，后端会优先使用 PaddleOCR 提取文本证据。
- 普通业务页面选择 `business_image`，主要用于多模态页面分析。
- 支持选择、粘贴、拖拽和多张图片上传；每张图片会独立上传，不会覆盖前一张。
- 首次 OCR 模型加载较慢时，进度区会提示耐心等待。

## 公告配置

公告来自 `notice_config.json`。可使用：

- `{app_release_label}`：产品名、版本和发布日期。
- `{app_version}`：客户端版本。
- `{app_release_date}`：发布日期。
- `{backend_url}`：打包时写入的后端地址。

也可以把新的 `notice_config.json` 放到 `FaultAnalyzerClient.exe` 同目录，客户端会优先读取外部配置。

## 测试

```powershell
python -m unittest discover -s windows-client\tests -v
```

若客户端能打开但无法执行功能，先确认已登录，再检查打包地址是否可访问，以及后端 `/health/ready` 是否返回 200。

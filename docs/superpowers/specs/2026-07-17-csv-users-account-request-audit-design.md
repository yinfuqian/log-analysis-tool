# CSV 用户、账号申请与操作审计设计

## 目标

将用户管理从密码哈希 JSON 改为便于管理员维护的明文 CSV，并保持热加载和已有会话立即失效。网页与 Windows 客户端均提供匿名账号申请入口，通过可配置通知适配器转发申请，不在本地或数据库保存申请内容。所有 API 操作写入数据库审计表，但不记录密码、Token、请求正文或上传内容。

## 用户 CSV

配置继续使用 `AUTH_USERS_FILE`，推荐值 `/data/users.csv`。格式：

```csv
username,password,status
admin,Admin@123,1
disabled,Password@123,0
forced_offline,Password@456,2
```

- `status=1`：允许登录。
- `status=0`：禁用，已有会话立即失效。
- `status=2`：强制下线并禁止登录，直到改回 `1`。
- 新增、删除、改密、改状态均通过文件身份变化触发热加载，无需重启。
- 用户名去除首尾空格并转为小写；空用户名、重复用户名、非法状态或空密码导致本次热加载失败，并保留上一份有效快照。
- 会话只保存稳定的密码指纹和用户名，不保存明文密码。密码变化、用户删除或状态不为 `1` 时，会话立即失效。

## 页面与接口授权

前端静态页面和业务路由允许匿名打开。匿名用户调用业务功能时，后端返回 `401`，网页提示登录，Windows 客户端返回登录窗口。

匿名白名单仅包含：

- `POST /auth/login`
- `POST /auth/account-requests`
- `/health/*`
- CORS `OPTIONS`

其他后端业务接口全部要求有效 Bearer Token。携带合法 Token 的调用均视为授权调用，不区分浏览器、Windows 客户端或 Postman。

## 账号申请

网页登录页和 Windows 登录窗口都增加“申请账号”。输入字段只有：

- `username`
- `password`
- `applicant_name`

后端生成 `request_id` 和带时区的 `requested_at`，随后调用通知适配器。申请内容不写本地文件、不写业务数据库。

通知配置：

```env
ACCOUNT_REQUEST_PROVIDER=mock
ACCOUNT_REQUEST_API_URL=
ACCOUNT_REQUEST_API_TOKEN=
ACCOUNT_REQUEST_API_TIMEOUT=10
```

- `mock`：不访问网络、不保存申请，返回模拟消息编号。
- `http`：将用户名、密码、申请人姓名、申请编号和申请时间作为 JSON 转发到配置地址；可选 Bearer Token。
- 调用失败统一返回“账号申请失败，请联系管理员”，不保存失败申请。
- 密码不进入任何日志。

## 操作审计表

新增 `user_operation_logs`：

- `id`
- `request_id`
- `operator_username`
- `actor_type`
- `request_method`
- `request_path`
- `client_ip`
- `user_agent`
- `status_code`
- `duration_ms`
- `operation_result`
- `target_username`
- `created_at`

请求开始时生成请求编号和计时信息，响应完成后写库：

- 已登录业务调用记录当前用户名。
- 登录记录尝试用户名及成功/失败。
- 账号申请记录申请用户名，操作者类型为 `anonymous`。
- 未授权调用记录匿名来源和 `401`。
- 健康检查与 `OPTIONS` 不记录。
- 审计写库失败只写应用错误日志，不改变原业务响应。

## 安全边界

- 明文密码只持久化在管理员维护的 `users.csv`。
- 登录和申请密码会在请求处理内存中短暂存在；客户端提交完成后清空输入。
- Redis、MySQL 操作日志、浏览器存储、客户端磁盘和应用日志均不保存密码。
- HTTP 通知提供方是否保存密码由第三方控制，生产必须使用 HTTPS。
- `users.csv` 必须限制为管理员与后端服务账号可读。

## 验证

- CSV 解析、热加载、状态切换、改密和删除用户测试。
- 匿名页面访问、业务 API `401`、登录后成功测试。
- Mock/HTTP 通知成功和失败测试，断言无本地申请记录。
- 网页和 Windows 账号申请表单测试。
- 操作日志字段、敏感信息排除、写库失败不影响响应测试。
- 后端、前端、Windows 客户端完整回归与生产构建。

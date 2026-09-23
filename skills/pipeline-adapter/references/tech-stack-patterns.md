# 各技术栈详细模式与一致性检查

本文档包含 Go、Java、Web、Python 等项目在接入流水线时的编译、启动、路径配置规范。
在生成对应技术栈的文件后，**必须按本文件逐项核对**。

## 通用编译制品输出规范

最后一个 `FROM scratch` 阶段，必须将制品复制到以下规范目录。目录结构为固定规范：

| 目录 | 用途 | 示例 |
|------|------|------|
| `/app/bin/` | 二进制运行程序 | Go/Python/Node 主程序 |
| `/app/bin/apprt` | 启动脚本 | 容器入口脚本（未接入 apprt 时需自行提供） |
| `/app/lib/` | 库包存放 | Java jar 包、前端 dist 目录 |
| `/app/share/` | 运行时依赖的中间件 | JDK（由 runtime-interpreter 自动注入）、Python 解释器、Node 等 |
| `/app/etc/` | 配置文件 | nginx.conf 等 |
| `/app/resources/` | 应用内置数据 | 静态资源 |
| `/app/app.json` | **必须** | 服务配置声明文件 |

**重要**：以上目录是制品在镜像内部的**固定存放规范**。但 `apprt` 启动脚本在运行时不应假设自身一定位于 `/app/bin/apprt`，而应通过 `WORKDIR="$( cd "$( dirname "$0"  )" && pwd  )"` 自推导脚本所在位置，所有运行时路径均相对于 `WORKDIR` 计算。

## Go 项目

### 编译要求
- **【必须】静态编译**：`CGO_ENABLED=0`，并添加 `-ldflags '-extldflags "-static"'`
- **Dockerfile** 将二进制产物拷贝到 `/app/bin/`
- **apprt** 通过 `WORKDIR` 自推导路径执行 `${WORKDIR}/${MODULE_NAME}`（`apprt` 位于 `/app/bin/apprt`，`dirname $0` 得到 `/app/bin`）

### 多架构交叉编译示例（build.sh）
```bash
if [[ "$TARGETARCH" == 'arm64' ]]; then
  CGO_ENABLED=1
  CC=aarch64-linux-gnu-gcc
  CC_FOR_TARGET=gcc-aarch64-linux-gnu
else
  CGO_ENABLED=0
fi
GOOS=linux GOARCH=$TARGETARCH
go build -a -installsuffix cgo -ldflags "-s -w ..." -o ${OUTPUT_BIN_EXE_FILE}
```

## Java 项目

### Dockerfile
- 将 jar 包拷贝到 `/app/lib/`
- **禁止**在 Dockerfile 中手动 COPY JDK

### app.json
```json
"runtime-interpreter": [
  { "name": "jdk", "version": "1.8", "type": "JavaRunTimeEnv" }
]
```
流水线会根据该字段**自动将 JDK 注入**到 `${APP_DIR}/share/jdk`。
`type` 可选值：`ReverseProxy`、`WebContainer`、`JavaRunTimeEnv`、`PythonInterpreter`。

### apprt
- `JAVA_HOME` 应相对于 `WORKDIR` 推导：`JAVA_HOME="${WORKDIR}/../share/jdk"`（**禁止**使用 `../share/jre`）
- 启动命令：`"${WORKDIR}/../share/jdk/bin/java" -jar "${WORKDIR}/${MODULE_NAME}.jar"`
- **禁止**在 apprt 中硬编码 `JAVA_HOME=/app/share/jdk` 或 `/app/lib/xxx.jar`

### 国产化运行时中间件（TongWeb / BES）
在 `app.json` 的 `containers.spec[]."runtime-interpreter"` 中声明：
```json
"runtime-interpreter": [
  { "name": "bes-appserver", "version": "9.5", "type": "WebContainer" }
]
```

**apprt 启动脚本必须增加转换调用**（使用相对路径）：
```bash
start_service(){
    if [ "${SPRING_BOOT_STARTER}" == "tongweb" ] \&\& [ -f "${WORKDIR}/../share/tongweb/tongweb-transform/tongweb-transform.sh" ]; then
        sh "${WORKDIR}/../share/tongweb/tongweb-transform/tongweb-transform.sh" "${WORKDIR}/${MODULE_NAME}.jar"
    elif [ "${SPRING_BOOT_STARTER}" == "bes-appserver" ] \&\& [ -f "${WORKDIR}/../share/bes-appserver/bes-appserver-transform.sh" ]; then
        sh "${WORKDIR}/../share/bes-appserver/bes-appserver-transform.sh" "${WORKDIR}/${MODULE_NAME}.jar"
    fi
    "${WORKDIR}/../share/jdk/bin/java" ${JAVA_TOOL_OPTIONS} -jar "${WORKDIR}/${MODULE_NAME}.jar" ${JAVA_OPTS}
}
```

**License 更新**：
- **Docker 版本**：将 license 文件拷贝到持久化目录（如 `/data/volumes/reverse-proxy-license`）。
- **K8S 版本**：将 license 内容更新到 `configmap` 中 `license` 的 `DATA` 字段内。

### 检查点
1. `pom.xml` 中 `finalName` 必须与 `apprt` 中 `java -jar` 后面的 jar 包名称一致
2. `pom.xml` 中 `outputDirectory` 必须与 `Dockerfile` 中 `COPY` 的源路径一致
3. `Dockerfile` 中 `COPY` 的目标路径必须与 `apprt` 中 jar 包路径一致
4. **`application.yml`（或 `application.yaml`）中的变量必须与 `app.json` 中 `environments.data[].name` 保持一致**：`${XXX}` 或 `@XXX@` 中的 `XXX` 必须在 `app.json` 中有对应 `name` 声明

## Web 前端项目

### Dockerfile
- 将 `npm run build` 产物（通常是 `dist/`）拷贝到 `/app/html/` 或 `/app/lib/dist/`

### app.json
若使用 nginx / tonghttpserver 作反向代理：
```json
"runtime-interpreter": [
  { "name": "nginx", "version": "1.23", "type": "ReverseProxy" }
]
```

### 国产化反向代理（TongHttpServer）
```json
"runtime-interpreter": [
  { "name": "tonghttpserver", "version": "1.0", "type": "ReverseProxy" }
]
```

**License 更新**：
- **Docker 版本**：将 license 文件拷贝到持久化目录。
- **K8S 版本**：将 license 内容更新到 `configmap` 中 `license` 的 `DATA` 字段内。

### 检查点
1. `package.json` 中的构建输出目录必须与 `Dockerfile` 中 `COPY` 的源路径一致
2. `Dockerfile` 中 `COPY` 的目标路径必须与 `apprt` 中 nginx 配置的 `root` 路径一致
3. **`nginx.conf`（或 `default.conf`）中的变量必须与 `app.json` 中 `environments.data[].name` 保持一致**：`$XXX` 或 `${XXX}` 中的 `XXX` 必须在 `app.json` 中有对应 `name` 声明

## Python 项目

### Dockerfile
- 将 Python 环境拷贝到 `/app/share/python`

### build.sh
```bash
pip3 install -i https://pkg.in.wezhuiyi.com/repository/pypi/simple -r requirements.txt
```

### apprt
```bash
${WORKDIR}/share/python/bin/python3 ${WORKDIR}/bin/{{MODULE_NAME}}.py
```

### 检查点
1. `build.sh` 中安装依赖的目标路径必须与 `Dockerfile` 中 `COPY` 的源路径一致
2. `Dockerfile` 中 `COPY` 的目标路径必须与 `apprt` 中 Python 解释器路径一致

## 定制化解析器环境（国产化 JDK / Python）
若需替换为指定发行版本：
- JDK 定制版 → `{"name": "...", "version": "...", "type": "JavaRunTimeEnv"}`
- Python 定制版 → `{"name": "...", "version": "...", "type": "PythonInterpreter"}`

# Dockerfile v3 规范速查

## 强制要求
1. **最后一个 `FROM` 必须是 `scratch`**。
   - 违反则编译报错。
2. **多架构编译支持**：编译阶段可使用 `--platform=${TARGETARCH}` 或固定的 `--platform=linux/amd64`。
3. **必须将 `app.json` 复制到 `/app/app.json`**。
   - 流水线根据 `app.json` 生成运行时镜像。
4. **未接入 `apprt` 配置中心时**：必须将自定义 `apprt` 脚本复制到 `/app/bin/apprt`。
   - 接入标准：代码仓库根目录下存在 `deployments/apprt/apprt.json`。

## 编译阶段说明
**编译阶段可完全根据项目情况自定义**：可以直接在 Dockerfile 中写 `RUN go build`、`RUN mvn package`、`RUN make build`、`RUN npm run build` 等，也可以通过 `build.sh` 脚本封装复杂逻辑。模板中的 `build.sh` 仅为示例，不是强制要求。**唯一约束是最终制品必须按规范复制到 `/app/*` 目录**。

## 推荐目录结构（二进制镜像中）
```
/app/
├── bin/
│   ├── apprt          # 启动脚本（未接配置中心时）
│   └── <binary>       # 编译产物
├── etc/
│   └── <config files>
├── deployments/       # 运行时依赖脚本
└── app.json           # 运行时镜像描述
```

## 典型流程
```dockerfile
ARG MODULE_GROUP="demo"
ARG MODULE_NAME="go-demo"
ARG SRC_DIR="/src"

FROM --platform=${TARGETARCH} registry01.wezhuiyi.com/standard/centos-builder:v1.8.0 as builder
ARG COMMIT
ARG MODULE_NAME
ARG SRC_DIR
ARG TARGETARCH
ENV GOPROXY http://pkg.in.wezhuiyi.com/repository/golang/,direct
ENV GOPRIVATE code.in.wezhuiyi.com
ENV GOSUMDB off
ENV GO111MODULE on
COPY . $SRC_DIR
WORKDIR $SRC_DIR
RUN chmod +x build_files/build.sh && bash -x ./build_files/build.sh ${MODULE_NAME} ${COMMIT} ${TARGETARCH}

FROM scratch
ARG MODULE_GROUP
ARG MODULE_NAME
ARG SRC_DIR
ENV APP_DIR="/app"
COPY --from=builder /${SRC_DIR}/${MODULE_NAME} /${APP_DIR}/bin/
COPY --from=builder /${SRC_DIR}/deployments/binary/apprt /${APP_DIR}/bin/apprt
COPY --from=builder /${SRC_DIR}/deployments/binary/ /${APP_DIR}/deployments/
COPY --from=builder /src/app.json /${APP_DIR}/app.json
```

## Web 前端项目示例
```dockerfile
ARG MODULE_NAME="web-demo"
ARG BUILD_DIR="/tmp/web-demo"

FROM --platform=${TARGETARCH} registry01.wezhuiyi.com/library/node:12.19.1-alpine3.12 AS builder
ARG BUILD_DIR
ARG TARGETARCH
WORKDIR ${BUILD_DIR}
COPY ./package*.json ./
COPY ./vendor ./vendor
ENV SASS_BINARY_PATH ${BUILD_DIR}/vendor/node-sass/...
COPY . .
RUN sh build_files/build.sh ${BUILD_DIR}

FROM scratch
ARG MODULE_NAME
ARG BUILD_DIR="/tmp/web-demo"
ENV APP_DIR="/app"
COPY --from=builder ${BUILD_DIR}/dist.tar.gz /${APP_DIR}/lib/dist.tar.gz
COPY --from=builder ${BUILD_DIR}/deployments/binary/apprt /${APP_DIR}/bin/apprt
COPY --from=builder ${BUILD_DIR}/app.json /${APP_DIR}/app.json
```

## 注意
- `build.sh` 需要接收并处理 `TARGETARCH` 参数以支持交叉编译。
- 如有额外配置文件或大模型资源，按规范放到 `/app/etc/` 或声明 `runtime-dep-resources`。

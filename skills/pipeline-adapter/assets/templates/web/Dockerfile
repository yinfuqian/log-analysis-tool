# Dockerfile
# 描述如何构建镜像，此文件准确描述服务如何构建及运行
# 语法参考文档：https://docs.docker.com/engine/reference/builder/
#
# 【重要说明】
# 本文件为前端（Web）项目模板，编译方式可灵活调整：
# - 使用 npm run build、yarn build 等构建
# - 输出通常为 dist/ 或 build/ 目录
#
# 【编译制品镜像输出规范 - 必须遵守】
# ${APP_DIR} 为容器内制品存放根目录，默认值为 `/app`，平台可通过 `--build-arg APP_DIR=/xxx` 覆盖。
# 前端项目制品存放：
# - ${APP_DIR}/lib/dist/        构建输出的静态资源
# - ${APP_DIR}/bin/apprt        启动脚本（nginx 配置）
# - ${APP_DIR}/app.json         【必须】服务配置声明文件
#
# 示例：
#   COPY --from=builder /src/dist ${APP_DIR}/lib/dist
#   COPY --from=builder /src/dist.tar.gz ${APP_DIR}/lib/dist.tar.gz
#   COPY --from=builder /src/app.json ${APP_DIR}/app.json

# TODO: 改这里为产品/组件名
ARG MODULE_GROUP="{{MODULE_GROUP}}"
# TODO: 改这里为模块名
ARG MODULE_NAME="{{MODULE_NAME}}"
# TODO: 构建根目录
ARG BUILD_DIR="/tmp/{{MODULE_NAME}}"

# Node 构建容器
# TODO: 默认无私库代理认证，需要认证请使用 node-builder 镜像
# FROM --platform=${TARGETARCH} registry01.wezhuiyi.com/library/node-builder:12.19.1-alpine3.12 AS builder
FROM --platform=${TARGETARCH} registry01.wezhuiyi.com/library/node:12.19.1-alpine3.12 AS builder

ARG BUILD_DIR
ARG TARGETARCH

WORKDIR ${BUILD_DIR}

#TODO: 先安装依赖，在依赖不变的情况下此层会使用cache,视情况修改
COPY ./package*.json ./
COPY ./vendor ./vendor
ENV SASS_BINARY_PATH ${BUILD_DIR}/vendor/node-sass/v4.14.1/linux_musl-x64-72_binding.node

# 编译
COPY . .
RUN sh build_files/build.sh ${BUILD_DIR}

# 构建二进制镜像，最后一个FROM必须为scratch
FROM scratch
ARG MODULE_GROUP
ARG MODULE_NAME
# TODO: 需要修改的路径
ARG BUILD_DIR="/tmp/{{MODULE_NAME}}"

# TODO: APP_DIR 为容器内制品存放根目录，平台可通过 --build-arg 覆盖，apprt 脚本应使用相对路径自推导
ARG APP_DIR="/app"

# TODO: 从构建阶段拷贝需要的产出文件到二进制镜像中
COPY --from=builder ${BUILD_DIR}/dist.tar.gz /${APP_DIR}/lib/dist.tar.gz

# TODO 拷贝配置文件（如有）
# COPY --from=builder ${BUILD_DIR}/deployments/binary/entrypoint.d/custom.conf.template /${APP_DIR}/etc/custom.conf.template

# 必须：未接入apprt配置中心时，需要将自定义apprt脚本复制到bin下
COPY --from=builder ${BUILD_DIR}/deployments/binary/apprt /${APP_DIR}/bin/apprt

# 必须：将app.json复制到/app下，流水线会根据它生成运行时镜像
COPY --from=builder ${BUILD_DIR}/app.json /${APP_DIR}/app.json

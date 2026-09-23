# Dockerfile
# 描述如何构建镜像，此文件准确描述服务如何构建及运行
# 语法参考文档：https://docs.docker.com/engine/reference/builder/
#
# 【重要说明】
# 本文件为模板示例，实际编译过程请根据项目技术栈灵活调整：
# - Go 项目：可使用 build.sh、Makefile、或直接在 RUN 中执行 go build
# - Java 项目：可使用 mvn package、mvn clean install 等
# - 前端项目：可使用 npm run build、yarn build 等
# - Python 项目：可使用 pip install 安装依赖
#
# 【编译制品镜像输出规范 - 必须遵守】
# 最后一个 FROM scratch 阶段，必须将制品复制到以下规范目录。
# ${APP_DIR} 为容器内制品存放根目录，默认值为 `/app`，平台可通过 `--build-arg APP_DIR=/xxx` 覆盖。
# apprt 启动脚本禁止硬编码绝对路径，应通过 WORKDIR="$( cd "$( dirname "$0"  )" && pwd  )" 自推导。
#
# 目录（相对 ${APP_DIR}）   用途                    示例
# ${APP_DIR}/bin/          二进制运行程序           Go/Python/Node 主程序
# ${APP_DIR}/bin/apprt     启动脚本                 容器入口脚本（未接入apprt时需自行提供）
# ${APP_DIR}/lib/          库包存放                 Java jar 包、前端 dist 目录
# ${APP_DIR}/share/        运行时依赖的中间件        JDK(由runtime-interpreter自动注入)、Python 解释器、Node 等
# ${APP_DIR}/etc/          配置文件                 nginx.conf 等
# ${APP_DIR}/resources/    应用内置数据             静态资源
# ${APP_DIR}/app.json      【必须】                 服务配置声明文件
#
# 示例：
#   Go:     COPY --from=builder /src/demo ${APP_DIR}/bin/
#   Java:   COPY --from=builder /src/target/demo.jar ${APP_DIR}/lib/
#   前端:   COPY --from=builder /src/dist ${APP_DIR}/lib/dist
#   Python: COPY --from=builder /opt/python ${APP_DIR}/share/python

# ========== 编译阶段（可灵活调整）==========
ARG MODULE_GROUP="{{MODULE_GROUP}}"
ARG MODULE_NAME="{{MODULE_NAME}}"
ARG SRC_DIR="/src"

# 临时构建容器，建议源为一个干净或带了通用依赖的基础镜像
FROM --platform=${TARGETARCH} registry01.wezhuiyi.com/standard/centos-builder:v1.8.0 as builder
ARG COMMIT
ARG MODULE_NAME
ARG SRC_DIR
ARG TARGETARCH

# TODO: 根据实际情况声明编译环境变量
ENV GOPROXY http://pkg.in.wezhuiyi.com/repository/golang/,direct
ENV GOPRIVATE code.in.wezhuiyi.com
ENV GOSUMDB off
ENV GO111MODULE on

# 拷贝源码
COPY . $SRC_DIR
WORKDIR $SRC_DIR

# TODO: 【编译方式灵活选择】以下是示例，可根据实际项目调整：
# - Go:    RUN CGO_ENABLED=0 go build -ldflags '-extldflags "-static"' -o ${MODULE_NAME}  # 【必须】CGO_ENABLED=0 和 -ldflags 启用静态编译
# - Go:    RUN make build
# - Java:  RUN mvn package -DskipTests
# - 前端:   RUN npm install && npm run build
# - Python: RUN pip install -r requirements.txt -t /opt/python
RUN chmod +x build_files/build.sh && bash -x ./build_files/build.sh ${MODULE_NAME} ${COMMIT} ${TARGETARCH}

# ========== 运行时阶段（必须符合规范）==========
# 【强制】最后一个 FROM 必须为 scratch
# 【注意】scratch 镜像不包含任何系统库，要求二进制文件必须静态编译（Go 项目必须 CGO_ENABLED=0）
# 【注意】APP_DIR 为容器内制品存放根目录，平台可通过 --build-arg 覆盖，apprt 脚本应使用相对路径自推导
FROM scratch
ARG MODULE_GROUP
ARG MODULE_NAME
ARG SRC_DIR
ARG APP_DIR="/app"

# TODO: 【按规范存放制品】根据技术栈选择正确的 COPY 路径：
# Go 项目 - 二进制文件复制到 ${APP_DIR}/bin/
COPY --from=builder /${SRC_DIR}/${MODULE_NAME} /${APP_DIR}/bin/

# TODO: 启动脚本复制到 /app/bin/apprt（未接入apprt时必须）
COPY --from=builder /${SRC_DIR}/deployments/binary/apprt /${APP_DIR}/bin/apprt

# TODO: 其他依赖文件
COPY --from=builder /${SRC_DIR}/deployments/binary/ /${APP_DIR}/deployments/

# TODO: 配置文件（如有）
# COPY --from=builder /${SRC_DIR}/deployments/apprt/apprt.json ${APP_DIR}/etc/apprt.json
COPY --from=builder /src/{{MODULE_NAME}}.conf /${APP_DIR}/etc/{{MODULE_NAME}}.conf

# 【强制】必须将 app.json 复制到 /app 下，流水线根据它生成运行时镜像
COPY --from=builder /src/app.json /${APP_DIR}/app.json

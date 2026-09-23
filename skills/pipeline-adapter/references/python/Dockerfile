# Dockerfile
# 描述如何构建镜像，此文件准确描述服务如何构建及运行
#
# 【编译制品镜像输出规范】
# 制品存放路径由平台决定，以下为默认值，apprt 脚本应使用相对路径自推导：
# - <APP_DIR>/share/python/    Python 解释器及所有依赖
# - <APP_DIR>/lib/             项目源码
# - <APP_DIR>/bin/apprt        启动脚本
# - <APP_DIR>/app.json         服务配置声明文件（必须）

# ---- 编译阶段 ----
ARG APP_DIR="/app"
ARG PYTHON_RUNTIME_DIR="${APP_DIR}/share/python"
# --platform=${TARGETARCH}
FROM --platform=${TARGETARCH} registry01.wezhuiyi.com/library/common-binary:latest as commonbin
FROM --platform=${TARGETARCH} registry01.wezhuiyi.com/standard/centos-builder:v1.6.0 as builder

ARG SRC_DIR="/src"
ARG MODULE_NAME="{{MODULE_NAME}}"
ARG PYTHON_RUNTIME_DIR

# 拷贝源码到构建容器
COPY . $SRC_DIR
WORKDIR $SRC_DIR

# 1. 使用 pyenv 的 Python 3.8 创建临时虚拟环境
# 2. 把临时 venv 移动到目标目录
# 3. 复制 Python 3.8 标准库和 include 到目标目录（venv 默认不含完整标准库，uWSGI 编译需要 include）
# 4. 修改 pyvenv.cfg 使 home 指向目标目录
RUN PYTHON38_DIR="/opt/pyenv/versions/3.8.18" && \
    ${PYTHON38_DIR}/bin/python3 -m venv --copies /tmp/venv && \
    mkdir -p $(dirname ${PYTHON_RUNTIME_DIR}) && \
    mv /tmp/venv ${PYTHON_RUNTIME_DIR} && \
    # 修复 bin/ 下所有脚本的 shebang
    sed -i "s|/tmp/venv|${PYTHON_RUNTIME_DIR}|g" ${PYTHON_RUNTIME_DIR}/bin/* && \
    # 复制标准库（保留 venv 自身的 site-packages）
    for item in ${PYTHON38_DIR}/lib/python3.8/*; do \
        name=$(basename "$item"); \
        if [[ "$name" != "site-packages" ]]; then \
            cp -rL "$item" ${PYTHON_RUNTIME_DIR}/lib/python3.8/; \
        fi; \
    done && \
    # 复制 include 目录（uWSGI 等包编译需要 Python.h）
    cp -rL ${PYTHON38_DIR}/include ${PYTHON_RUNTIME_DIR}/ && \
    # 删除 pyvenv.cfg，避免 home 硬编码为构建时绝对路径，导致运行时目录被移动后找不到标准库
    rm -f ${PYTHON_RUNTIME_DIR}/pyvenv.cfg

# 在虚拟环境中安装项目依赖
RUN ${PYTHON_RUNTIME_DIR}/bin/python3 -m pip install -i https://pkg.in.wezhuiyi.com/repository/pypi/simple -r requirements.txt

# 将虚拟环境中的符号链接替换为实际文件（scratch 镜像中无系统路径）
RUN find ${PYTHON_RUNTIME_DIR} -type l | while read link; do \
        target=$(readlink -f "$link"); \
        if [[ -f "$target" ]]; then \
            rm -f "$link"; \
            cp -pf "$target" "$link"; \
        elif [[ -d "$target" ]]; then \
            rm -f "$link"; \
            cp -rpf "$target" "$link"; \
        fi; \
    done

# 确保启动脚本有执行权限（COPY 到 scratch 后会保留）
RUN chmod +x ${SRC_DIR}/deployments/binary/apprt

# 下载远端 portable.sh 并对 Python 虚拟环境进行便携化处理
# 该脚本会分析 ELF 依赖、拷贝系统库、修改 rpath/interpreter，使环境可在 scratch 镜像中运行
COPY --from=commonbin /app/bin/ /usr/local/bin/
RUN sh /usr/local/bin/install_busybox_subcmd && \
    wget -q -O /tmp/portable.sh http://pkg.in.wezhuiyi.com/repository/infra/portable/v2/portable.sh && \
    bash /tmp/portable.sh --with-feature=all --trace ${PYTHON_RUNTIME_DIR}

# ---- 运行阶段（最后一个 FROM 必须为 scratch）----
FROM scratch
ARG MODULE_GROUP
ARG MODULE_NAME
ARG SRC_DIR="/src"
ARG PYTHON_RUNTIME_DIR
ARG APP_DIR="/app"

# 必须：拷贝 app.json 到镜像中
COPY --from=builder ${SRC_DIR}/app.json ${APP_DIR}/app.json

# 拷贝项目源码
COPY --from=builder ${SRC_DIR}/app ${APP_DIR}/lib/app/
COPY --from=builder ${SRC_DIR}/my_app.py ${APP_DIR}/lib/

# 拷贝包含依赖的完整 Python 环境
COPY --from=builder ${PYTHON_RUNTIME_DIR} ${APP_DIR}/share/python/

# 拷贝启动脚本
COPY --from=builder ${SRC_DIR}/deployments/binary/apprt ${APP_DIR}/bin/apprt

#!/usr/bin/env bash
# Content: 该脚本为编译入口
# 注意此文件只能在项目根目录下执行
# TODO: 该文件需要研发根据自己模块的实际情况书写对应模块的脚本，下面的代码仅为样例，并不能覆盖所有场景

# 第一个位置参数为待输出的二进制文件名字参数
OUTPUT_BIN_EXE_FILE=${1:-"{{MODULE_NAME}}"}
PROJECT=${OUTPUT_BIN_EXE_FILE}
# 第二个位置参数为当前构建的commitid
COMMIT=${2:-$(git rev-parse --short HEAD)}
MODULE_DIR=${3:-"/app"}

# 下面为编译的命令，最终输出文件可执行文件${OUTPUT_BIN_EXE_FILE}
# TODO 注意 安装完项目依赖后一定要执行bash /opt/python-app-build.sh，会将当前项目的依赖和当前python环境构造成静态环境，
# TODO 注意 /opt/pyenv/versions/3.8目录（或具体的3.8.x子目录）就是包含了依赖的完整的python环境
BUILD_CMD="pip3 install -i https://pkg.in.wezhuiyi.com/repository/pypi/simple -r requirements.txt && bash /opt/python-app-build.sh"

# =tar==================此中间部分脚本为tar包部署内容=======================tar=
_help() {
    echo "eg: bash build_files/build.sh"
    echo "eg: bash build_files/build.sh container-build"
    echo "eg: bash build_files/build.sh binary-package"
}

# 本地容器构建二进制文件
container_build(){
    PROJECT="{{MODULE_NAME}}"
    APP_DIR="${MODULE_DIR}"
    if [[ ${COMMIT} == "" ]]; then
        COMMIT="latest"
    fi
    if command -v docker >/dev/null 2>&1; then
        CONTAINER_NAME="${PROJECT}-build-time"
        BUILD_CMD="docker build -t ${PROJECT}:${COMMIT} . && docker run --rm --name ${CONTAINER_NAME} --entrypoint cat -itd ${PROJECT}:${COMMIT} && docker cp ${CONTAINER_NAME}:${APP_DIR}/bin/${PROJECT} . && docker rm ${CONTAINER_NAME} -f"
    fi
}
# tar包部署时打包
binary_package(){
    PROJECT="{{MODULE_NAME}}"
    local package_name="${PROJECT}.tar.gz"
    rm -f ${package_name} && tar -zcvf ${package_name} ${PROJECT} deployments/binary
}

case $1 in
--help | -h)
    _help
    exit 0
    ;;
container-build)
    container_build
    ;;
binary-package)
    binary_package
    exit 0
    ;;
*)
    echo ""
    ;;
esac
# =tar==================此中间部分脚本为tar包部署内容=======================tar=

echo "${BUILD_CMD}"
eval "${BUILD_CMD}" || (echo "build ${OUTPUT_BIN_EXE_FILE} failed!" && exit 1) && echo "build ${OUTPUT_BIN_EXE_FILE} success."

#!/usr/bin/env bash
# Content: 该脚本为编译入口
# 注意此文件只能在项目根目录下执行
# TODO: 该文件需要研发根据自己模块的实际情况书写对应模块的脚本，下面的代码仅为样例，并不能覆盖所有场景

# 第一个位置参数为构建根目录位置
BUILD_DIR=${1:-"."}

# =tar==================此中间部分脚本为tar包部署内容=======================tar=
_help() {
    echo "eg: bash build_files/build.sh"
    echo "eg: bash build_files/build.sh container-build"
    echo "eg: bash build_files/build.sh binary-package"
}

# 本地容器构建二进制文件
container_build(){
    COMMIT=${2:-$(git rev-parse --short HEAD)}
    PROJECT="{{MODULE_NAME}}"
    APP_DIR=${APP_DIR:-"/app"}
    if [[ ${COMMIT} == "" ]]; then
        COMMIT="latest"
    fi
    if command -v docker >/dev/null 2>&1; then
        CONTAINER_NAME="${PROJECT}-build-time"
        BUILD_CMD="docker build -t ${PROJECT}:${COMMIT} . && docker run --rm --name ${CONTAINER_NAME} --entrypoint cat -itd ${PROJECT}:${COMMIT} && mkdir -p dist && docker cp ${CONTAINER_NAME}:${APP_DIR}/lib/dist.tar.gz ./dist/ && docker rm ${CONTAINER_NAME} -f"
    fi
	echo "${BUILD_CMD}"
	eval "${BUILD_CMD}" || (echo "build ${PROJECT} failed!" && exit 1) && echo "build ${PROJECT} success."

}
# tar包部署时打包
binary_package(){
    PROJECT="{{MODULE_NAME}}"
    local package_name="${PROJECT}.tar.gz"
    rm -f ${package_name} && tar -zcvf ${package_name} dist/dist.tar.gz deployments/binary
}

case $1 in
--help | -h)
    _help
    exit 0
    ;;
container-build)
    container_build
    exit 0
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


# 下面为编译的命令，最终输出前端打包产物
npm --registry=https://registry.npmmirror.com install && npm run build && cd ${BUILD_DIR}/dist/ && tar -zcvf ${BUILD_DIR}/dist.tar.gz *

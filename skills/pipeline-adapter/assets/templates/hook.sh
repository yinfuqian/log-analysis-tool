#!/usr/bin/env bash
export PATH=${PATH}:/sbin:/usr/sbin:/usr/local/sbin:/usr/local/bin:/usr/bin:/bin
export TERM="xterm-256color"

# 脚本所在目录
SCRIPT_DIR=$(cd "$(dirname "$0")"; pwd)

# TODO: 修改为你需要导入数据时使用的镜像名称
IMPORT_IMAGE_NAME="infra/mysql-ms:5.7.30-custom"

# 日志文件路径
LOG_FILE="${SCRIPT_DIR}/.log/hooks.log"

declare -A ARGS_MAP

args_parser(){
    if [[ $# -eq 0 ]] ; then
        help_msg
        exit 0
    fi
    shift
    for item in "$@"
    do
        if [[ $(expr length "${item}") -gt 2 ]];then
            local config_str=$(echo "${item#--}")
            if [[ ! -n "${config_str}" ]];then
                warn "${item} is an invalid parameter"
                continue
            fi
            local key=$(echo "${config_str%%=*}" | sed "s/-/_/g" | tr 'A-Z' 'a-z')
            if [[ -n "${key}" ]];then
                local value=${config_str#*=}
                ARGS_MAP["${key}"]="${value}"
            fi
        else
            warn "${item} is an invalid parameter"
            continue
        fi
    done
    return 0
}

info() {
    tput bold ; tput setaf 2; date +"%F %T Info: $*" | tee -a ${LOG_FILE} ; tput sgr0
}

warn() {
    tput bold ; tput setaf 3; date +"%F %T Warning: $*" | tee -a ${LOG_FILE} ; tput sgr0
}

error() {
    tput bold ; tput setaf 1; date +"%F %T Error: $*" | tee -a ${LOG_FILE} ; tput sgr0
}

err_exit() {
    tput bold ; tput setaf 1; date +"%F %T Error: $*" | tee -a ${LOG_FILE} ; tput sgr0
    exit 1
}

exit_step_check(){
    if [[ $? -ne 0 ]] || [[ ${RS} -ne 0 ]];then
        err_exit "$* fail!!!"
    else
        info "$* success."
    fi
}

init_log(){
    if [[ ! -f "${LOG_FILE}" ]];then
        mkdir -p ${LOG_FILE%/*}
        touch ${LOG_FILE}
    fi
    return 0
}

help_msg(){
    info "help_msg"
    echo "Usage: bash hook.sh <command> [options]"
    echo "Commands: pre_install, post_install, pre_uninstall, post_uninstall"
}

load_image(){
    if [[ -d "${SCRIPT_DIR}/../../base/images/mysql-ms" ]];then
        info "Starting loading mysql image"
        docker load -i ${SCRIPT_DIR}/../../base/images/mysql-ms/image_*.tar.gz
    fi
}

import_data(){
    # TODO: 根据实际需求修改 SQL 文件名
    if [[ -n "${ARGS_MAP["mysql_master_host"]}" ]] && [[ -n "${ARGS_MAP["mysql_master_port"]}" ]] && [[ -n "${ARGS_MAP["mysql_master_user"]}" ]] && [[ -n "${ARGS_MAP["mysql_master_password"]}" ]];then
        load_image
        exit_step_check "load image"
        docker run --rm -i --net host -e USER_ID=${ARGS_MAP["user_id"]} -e GROUP_ID=${ARGS_MAP["group_id"]} \
            ${IMPORT_IMAGE_NAME} mysql -h ${ARGS_MAP["mysql_master_host"]} -P ${ARGS_MAP["mysql_master_port"]} \
            -u ${ARGS_MAP["mysql_master_user"]} -p${ARGS_MAP["mysql_master_password"]} \
            < ${SCRIPT_DIR}/resource/db_init.sql
        exit_step_check "import sql"
    fi
}

pre_install(){
    info "pre_install"
    import_data
}

post_install(){
    info "post_install"
}

pre_uninstall(){
    info "pre_uninstall"
}

post_uninstall(){
    info "post_uninstall"
}

init_log
args_parser "$@"

case $1 in
    pre_install )
        pre_install "$@"
        ;;
    post_install )
        post_install "$@"
        ;;
    pre_uninstall )
        pre_uninstall "$@"
        ;;
    post_uninstall )
        post_uninstall "$@"
        ;;
    -h | --help | help )
        help_msg
        ;;
    * )
        help_msg
        exit 1
        ;;
esac

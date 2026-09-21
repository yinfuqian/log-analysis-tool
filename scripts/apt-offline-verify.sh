# 本脚本在容器内断网验证离线 deb 依赖包：只从挂载的 deb 目录安装，缺少任何依赖或命令都会失败。
# 用法：sh apt-offline-verify.sh <Debian 发行版代号> <架构>
set -eu

release="${1:-}"
arch="${2:-}"
if [ -z "$release" ] || [ -z "$arch" ]; then
    echo "用法：sh apt-offline-verify.sh <Debian 发行版代号> <架构>" >&2
    exit 2
fi

deb_dir="/opt/apt-offline/${release}-${arch}"
if [ ! -d "$deb_dir" ]; then
    echo "离线 deb 目录不存在：$deb_dir" >&2
    exit 1
fi

dpkg -i "$deb_dir"/*.deb

for command_name in git curl bsdtar unzip; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "离线安装后仍缺少命令：$command_name" >&2
        exit 1
    fi
done

if ! command -v 7z >/dev/null 2>&1 && ! command -v 7zz >/dev/null 2>&1 && ! command -v 7za >/dev/null 2>&1; then
    echo "离线安装后仍缺少 7-Zip 系命令" >&2
    exit 1
fi

echo "离线安装自检通过：${release}/${arch}"

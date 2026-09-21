# 本脚本在 Debian 容器内运行，把后端镜像依赖的 apt 软件包连同递归依赖一起下载为离线 deb 包。
# 用法：sh apt-offline-download.sh <Debian 发行版代号> <apt 镜像源> <软件包...>
# 输出：/out/<发行版代号>-<架构>/ 下的 deb 包、MANIFEST.tsv 与 SHA256SUMS。
set -eu

release="${1:-}"
mirror="${2:-}"
if [ -z "$release" ] || [ -z "$mirror" ]; then
    echo "用法：sh apt-offline-download.sh <Debian 发行版代号> <apt 镜像源> <软件包...>" >&2
    exit 2
fi
shift 2

if [ "$#" -eq 0 ]; then
    echo "至少需要指定一个软件包" >&2
    exit 2
fi

arch="$(dpkg --print-architecture)"
target="/out/${release}-${arch}"

sources="/etc/apt/sources.list.d/debian.sources"
if [ ! -f "$sources" ]; then
    sources="/etc/apt/sources.list"
fi
if [ ! -f "$sources" ]; then
    echo "容器内未找到 apt 源文件，无法替换镜像源" >&2
    exit 1
fi
sed -i "s|http://deb.debian.org/debian|${mirror}|g; s|http://security.debian.org/debian-security|${mirror}-security|g" "$sources"

rm -rf "$target"
mkdir -p "$target"

apt-get update
apt-get install -y --no-install-recommends --download-only \
    -o Dir::Cache::archives="$target" \
    "$@"

rm -rf "$target/partial" "$target/lock"

# 基础镜像里已经安装的软件包不会被 --download-only 下载，但离线包必须覆盖完整清单，
# 否则基础镜像升级后离线包就不完整；这里用 apt-get download 单独补齐。
missing=""
for package_name in "$@"; do
    if ! ls "$target/${package_name}"_*.deb >/dev/null 2>&1; then
        missing="${missing} ${package_name}"
    fi
done
if [ -n "$missing" ]; then
    echo "补齐基础镜像中已安装的软件包：${missing}"
    (cd "$target" && apt-get download ${missing})
fi
rm -rf "$target/partial" "$target/lock"

if ! ls "$target"/*.deb >/dev/null 2>&1; then
    echo "没有下载到任何 deb 包" >&2
    exit 1
fi

cd "$target"
{
    printf '# %s/%s 离线 apt 依赖清单，由 scripts/apt-offline-download.sh 生成。\n' "$release" "$arch"
    printf '# 软件包\t版本\t架构\n'
    for deb in ./*.deb; do
        printf '%s\t%s\t%s\n' \
            "$(dpkg-deb -f "$deb" Package)" \
            "$(dpkg-deb -f "$deb" Version)" \
            "$(dpkg-deb -f "$deb" Architecture)"
    done | sort
} > MANIFEST.tsv

sha256sum ./*.deb > SHA256SUMS

echo "离线 deb 包输出目录：$target"
echo "包数量：$(ls -1 ./*.deb | wc -l)，总大小：$(du -sh . | cut -f1)"

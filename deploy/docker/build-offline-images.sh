#!/usr/bin/env bash
# 内网离线部署打包脚本（在可联网构建机上执行）。
#
# 功能：
#   1. 用 sqlite3 .backup 把本机数据库一致性快照到 deploy/docker/seed-data/
#      （即使本地服务正在运行也不会拷出脏数据）；
#   2. 构建主应用镜像（runtime）与 Mock 镜像（mock-runtime）；
#   3. docker save | gzip 导出到 offline-dist/，并生成 sha256 校验文件；
#   4. 打印目标机（纯内网）导入与启动指引。
#
# 用法：
#   bash deploy/docker/build-offline-images.sh            # 快照 + 构建 + 导出 + 打整包
#   bash deploy/docker/build-offline-images.sh snapshot   # 只更新数据库快照
#   bash deploy/docker/build-offline-images.sh build      # 只构建镜像（用已有快照）
#   bash deploy/docker/build-offline-images.sh export     # 只导出 tar.gz（用已有镜像）
#   bash deploy/docker/build-offline-images.sh bundle     # 只打整包（镜像 tar + 部署脚本 + .env + 主密钥）
#
# 目标架构（按架构分别出包，镜像 tag 与 tar 文件名均带架构后缀）：
#   PLATFORM=linux/amd64   # 默认，目标机为 x86_64（如麒麟 V10 x86_64）
#   PLATFORM=linux/arm64   # 目标机为 arm64/aarch64（如麒麟 V10 鲲鹏/飞腾）
#   x86_64 构建机交叉构建 arm64 依赖 Docker 自带 binfmt/QEMU，速度较慢属正常。
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$DEPLOY_DIR/../.." && pwd)"
SEED_DIR="$DEPLOY_DIR/seed-data"
# 产物输出目录：默认 offline-dist/，可按架构分目录（如 offline-dist/x86、offline-dist/arm64）
DIST_DIR="${DIST_DIR:-$PROJECT_ROOT/offline-dist}"
DATA_DIR="$PROJECT_ROOT/backend/data"
ACTION="${1:-all}"
PLATFORM="${PLATFORM:-linux/amd64}"
# 构建机访问默认 PyPI 不稳定时使用国内镜像；设为空字符串则走默认源。
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

die() {
    printf '错误: %s\n' "$*" >&2
    exit 1
}

case "$PLATFORM" in
    linux/amd64) ARCH="amd64" ;;
    linux/arm64) ARCH="arm64" ;;
    *) die "PLATFORM 仅支持 linux/amd64 或 linux/arm64，当前值: $PLATFORM" ;;
esac

APP_IMAGE="activity-analysis:latest-$ARCH"
MOCK_IMAGE="activity-analysis-mock:latest-$ARCH"
APP_TAR="activity-analysis-image-$ARCH.tar.gz"
MOCK_TAR="activity-analysis-mock-image-$ARCH.tar.gz"

snapshot() {
    command -v sqlite3 >/dev/null 2>&1 || die "未找到 sqlite3 命令，无法做数据库一致性快照"
    mkdir -p "$SEED_DIR"

    local db name
    for name in skills.db v3_checkpoints.db; do
        db="$DATA_DIR/$name"
        # 同时清掉残留的 WAL 副产物（手动 cp 活体库会留下它们；
        # 种子必须来自 sqlite3 .backup，直接 cp 的库可能不一致）
        rm -f "$SEED_DIR/$name" "$SEED_DIR/$name-shm" "$SEED_DIR/$name-wal"
        if [ -f "$db" ]; then
            echo "快照数据库: $name"
            sqlite3 "$db" ".backup '$SEED_DIR/$name'"
        else
            echo "警告: $db 不存在，跳过（目标机将自动创建空库）" >&2
        fi
    done
    ls -lh "$SEED_DIR"
}

build() {
    command -v docker >/dev/null 2>&1 || die "未安装 Docker"
    docker info >/dev/null 2>&1 || die "Docker 服务未启动（请先启动 Docker Desktop / dockerd）"
    [ -d "$SEED_DIR" ] || die "缺少 $SEED_DIR，请先执行 snapshot（或直接执行 all）"

    local host_arch
    host_arch="$(uname -m)"
    if { [ "$ARCH" = "arm64" ] && [ "$host_arch" = "x86_64" ]; } \
        || { [ "$ARCH" = "amd64" ] && [ "$host_arch" = "arm64" ]; }; then
        echo "提示: 当前为交叉构建（构建机 $host_arch -> 目标 $ARCH），"
        echo "      依赖 Docker 自带 binfmt/QEMU 模拟，构建速度较慢属正常现象。"
    fi

    echo "构建主应用镜像 ($PLATFORM): $APP_IMAGE"
    docker build --platform "$PLATFORM" \
        --build-arg "PIP_INDEX_URL=$PIP_INDEX_URL" \
        -f "$DEPLOY_DIR/Dockerfile" --target runtime \
        -t "$APP_IMAGE" "$PROJECT_ROOT"

    echo "构建 Mock 镜像 ($PLATFORM): $MOCK_IMAGE"
    docker build --platform "$PLATFORM" \
        --build-arg "PIP_INDEX_URL=$PIP_INDEX_URL" \
        -f "$DEPLOY_DIR/Dockerfile" --target mock-runtime \
        -t "$MOCK_IMAGE" "$PROJECT_ROOT"
}

export_images() {
    command -v docker >/dev/null 2>&1 || die "未安装 Docker"
    docker image inspect "$APP_IMAGE" >/dev/null 2>&1 || die "镜像 $APP_IMAGE 不存在，请先 build"
    docker image inspect "$MOCK_IMAGE" >/dev/null 2>&1 || die "镜像 $MOCK_IMAGE 不存在，请先 build"

    mkdir -p "$DIST_DIR"
    echo "导出: $DIST_DIR/$APP_TAR"
    docker save "$APP_IMAGE" | gzip > "$DIST_DIR/$APP_TAR"
    echo "导出: $DIST_DIR/$MOCK_TAR"
    docker save "$MOCK_IMAGE" | gzip > "$DIST_DIR/$MOCK_TAR"

    (
        cd "$DIST_DIR"
        if command -v shasum >/dev/null 2>&1; then
            shasum -a 256 "$APP_TAR" "$MOCK_TAR" > MANIFEST.sha256
        else
            sha256sum "$APP_TAR" "$MOCK_TAR" > MANIFEST.sha256
        fi
    )
    ls -lh "$DIST_DIR"

    cat <<EOF

============================================================
 打包完成。目标机（纯内网）操作步骤：
============================================================
1. 传输以下文件到目标机（如 /opt/activity-analysis/）：
   - $DIST_DIR/$APP_TAR
   - $DIST_DIR/$MOCK_TAR
   - $DIST_DIR/MANIFEST.sha256
   - 项目中的 deploy/docker/ 整个目录
   - 已配置好的 backend/.env

2. 目标机导入镜像并回标 latest（Compose 引用不带后缀的标签）：
   cd /opt/activity-analysis/offline-dist   # 按实际存放路径
   sha256sum -c MANIFEST.sha256
   gunzip -c $APP_TAR | docker load
   gunzip -c $MOCK_TAR | docker load
   docker tag $APP_IMAGE activity-analysis:latest
   docker tag $MOCK_IMAGE activity-analysis-mock:latest

3. 目标机启动（不要用 up，会触发联网构建）：
   cd deploy/docker
   bash docker-deploy.sh up-no-build

   首次启动时入口脚本会自动把镜像内的数据库种子
   （skills.db / v3_checkpoints.db）拷入 runtime-data 卷。

4. 验证：
   curl http://localhost:9111/activity/health   # {"status":"ok"}
============================================================
EOF
}

bundle() {
    [ -f "$DIST_DIR/$APP_TAR" ] || die "缺少 $DIST_DIR/$APP_TAR，请先执行 export（或 all）"
    [ -f "$DIST_DIR/$MOCK_TAR" ] || die "缺少 $DIST_DIR/$MOCK_TAR，请先执行 export（或 all）"
    [ -f "$PROJECT_ROOT/backend/.env" ] || die "缺少 backend/.env"

    local bundle_name="activity-analysis-offline-bundle"
    local bundle_root="$DIST_DIR/$bundle_name"
    rm -rf "$bundle_root"
    mkdir -p \
        "$bundle_root/offline-dist" \
        "$bundle_root/backend" \
        "$bundle_root/deploy/docker/secrets"

    # 镜像与校验文件
    cp "$DIST_DIR/$APP_TAR" "$DIST_DIR/$MOCK_TAR" "$DIST_DIR/MANIFEST.sha256" \
        "$bundle_root/offline-dist/"

    # 部署脚本（不含 runtime-data / seed-data / .env 等本地产物）
    local f
    for f in docker-compose.yml docker-deploy.sh docker-entrypoint.sh \
             Dockerfile Dockerfile.dockerignore DOCKER-SQLITE-DEPLOY.md .gitignore; do
        [ -f "$DEPLOY_DIR/$f" ] && cp "$DEPLOY_DIR/$f" "$bundle_root/deploy/docker/"
    done

    # 配置文件与主密钥（master.key 不存在说明未启用密文，跳过即可）
    cp "$PROJECT_ROOT/backend/.env" "$bundle_root/backend/.env"
    if [ -f "$PROJECT_ROOT/backend/data/secrets/master.key" ]; then
        cp "$PROJECT_ROOT/backend/data/secrets/master.key" \
            "$bundle_root/deploy/docker/secrets/master.key"
        chmod 600 "$bundle_root/deploy/docker/secrets/master.key"
    else
        echo "提示: 未发现 backend/data/secrets/master.key，整包不含主密钥" >&2
    fi

    # 服务器端一键安装脚本（镜像名/包名在生成时按架构代入）
    cat > "$bundle_root/install.sh" <<'INSTALL_EOF'
#!/usr/bin/env bash
# 内网服务器一键安装：校验并导入镜像，然后启动。
set -euo pipefail
cd "$(dirname "$0")"

command -v docker >/dev/null 2>&1 || { echo "错误: 未安装 Docker" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "错误: Docker 服务未启动" >&2; exit 1; }

cd offline-dist
sha256sum -c MANIFEST.sha256
gunzip -c __APP_TAR__ | docker load
gunzip -c __MOCK_TAR__ | docker load
cd ..

# Compose 编排引用的是不带架构后缀的 latest 标签，导入后回标
docker tag __APP_IMAGE__ activity-analysis:latest
docker tag __MOCK_IMAGE__ activity-analysis-mock:latest

bash deploy/docker/docker-deploy.sh up-no-build

PORT="$(sed -n 's/^PORT=//p' backend/.env | tail -1 | tr -d "\"'[:space:]")"
sleep 5
echo "健康检查: http://localhost:${PORT:-9111}/activity/health"
curl -s -m 10 "http://localhost:${PORT:-9111}/activity/health" && echo
INSTALL_EOF
    sed -i '' \
        -e "s|__APP_TAR__|$APP_TAR|g" \
        -e "s|__MOCK_TAR__|$MOCK_TAR|g" \
        -e "s|__APP_IMAGE__|$APP_IMAGE|g" \
        -e "s|__MOCK_IMAGE__|$MOCK_IMAGE|g" \
        "$bundle_root/install.sh" 2>/dev/null \
    || sed -i \
        -e "s|__APP_TAR__|$APP_TAR|g" \
        -e "s|__MOCK_TAR__|$MOCK_TAR|g" \
        -e "s|__APP_IMAGE__|$APP_IMAGE|g" \
        -e "s|__MOCK_IMAGE__|$MOCK_IMAGE|g" \
        "$bundle_root/install.sh"
    chmod +x "$bundle_root/install.sh"

    tar -czf "$DIST_DIR/$bundle_name-$ARCH.tar.gz" -C "$DIST_DIR" "$bundle_name"
    rm -rf "$bundle_root"

    ls -lh "$DIST_DIR/$bundle_name-$ARCH.tar.gz"
    cat <<EOF

============================================================
 整包完成: $DIST_DIR/$bundle_name-$ARCH.tar.gz  ($PLATFORM)
============================================================
1. 传输（只带这一个文件）：
   scp $DIST_DIR/$bundle_name-$ARCH.tar.gz user@服务器:/opt/

2. 服务器上解开并安装：
   cd /opt && tar -xzf $bundle_name-$ARCH.tar.gz
   cd $bundle_name && bash install.sh

   解开后即为完整目录结构（backend/.env、deploy/docker/、
   offline-dist/、secrets/master.key 均已就位），install.sh
   自动完成校验、docker load、回标 latest、启动与健康检查。
============================================================
EOF
}

case "$ACTION" in
    all)      snapshot; build; export_images; bundle ;;
    snapshot) snapshot ;;
    build)    build ;;
    export)   export_images ;;
    bundle)   bundle ;;
    *)        die "不支持的操作: $ACTION（可选 all、snapshot、build、export、bundle）" ;;
esac

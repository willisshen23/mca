#!/usr/bin/env bash
#
# P4 离线部署包两阶段验证（本机 Docker，macOS 可跑）
# 用法: bash offline-v3/verify.sh [包路径]   # 缺省取 offline-v3/dist/ 最新产物
# 前置: 宿主机 mock 营销接口已起 (:8005)；backend/.env 含有效 LLM_* 配置
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
V3_DIR="$ROOT_DIR/offline-v3"
if [ $# -ge 1 ]; then
    PKG="$1"
    [ -f "$PKG" ] || { echo "错误: 指定的部署包不存在: $PKG" >&2; exit 1; }
else
    # glob 无匹配时 ls 非零，pipefail 下赋值会静默被 set -e 杀死，故 || true 兜底
    PKG="$(ls -t "$V3_DIR"/dist/activity-analysis-assistant-offline-*.tar.gz 2>/dev/null | head -1 || true)"
    [ -n "$PKG" ] || { echo "错误: 未找到部署包，请先运行 offline-v3/build.sh" >&2; exit 1; }
fi
echo "验证目标: $PKG"

# 按包名架构后缀选择容器平台；跨架构验证依赖 Docker binfmt/QEMU（慢但可用）
case "$(basename "$PKG")" in
    *-arm64-*) VERIFY_PLATFORM="linux/arm64" ;;
    *)         VERIFY_PLATFORM="linux/amd64" ;;
esac
echo "验证平台: $VERIFY_PLATFORM（构建机 $(uname -m)，跨架构时走 QEMU 模拟）"

echo ""
echo ">>> 阶段 1/2: 断网离线安装验证 (debian:buster-slim, --network none)"
docker run --rm -i --platform "$VERIFY_PLATFORM" --network none \
    -v "$PKG":/pkg/package.tar.gz:ro \
    debian:buster-slim bash -s <<'STAGE1'
set -euo pipefail
cd /tmp
tar -xzf /pkg/package.tar.gz
cd activity-analysis-assistant
( cd offline-bundle && sha256sum -c MANIFEST.sha256 --quiet )
echo "MANIFEST 校验通过"
printf 'LLM_BASE_URL=http://placeholder.invalid/v1\nLLM_MODEL=placeholder\n' > backend/.env
tar -xzf offline-bundle/python/cpython-*.tar.gz -C offline-bundle/python
offline-bundle/python/python/bin/python3 -m venv backend/venv
backend/venv/bin/pip install --no-index --find-links=offline-bundle/wheels \
    -r backend/requirements-offline.txt
cd backend
./venv/bin/python -c "import src.main; print('IMPORT_OK: src.main')"
STAGE1
echo "阶段 1 通过: MANIFEST + 断网安装 + import src.main"

echo ""
echo ">>> 阶段 2/2: 业务冒烟 (联网容器 + 宿主机 mock:8005)"
ENV_FILE="$ROOT_DIR/backend/.env"
[ -f "$ENV_FILE" ] || { echo "错误: 缺少 $ENV_FILE" >&2; exit 1; }
# 从 .env 解析配置：容忍 export 前缀、等号两侧空白、值两侧单/双引号；
# 用 sed 而非 grep——grep 无命中返回非零，pipefail 下赋值会被 set -e 静默杀死
get_env() {
    sed -nE "s/^[[:space:]]*(export[[:space:]]+)?$1[[:space:]]*=[[:space:]]*//p" "$ENV_FILE" \
        | head -1 | sed -E "s/^'(.*)'$/\1/; s/^\"(.*)\"$/\1/"
}
LLM_BASE_URL="$(get_env LLM_BASE_URL)"
LLM_API_KEY="$(get_env LLM_API_KEY)"
LLM_MODEL="$(get_env LLM_MODEL)"
export LLM_BASE_URL LLM_API_KEY LLM_MODEL
for k in LLM_BASE_URL LLM_API_KEY LLM_MODEL; do
    [ -n "${!k}" ] || { echo "错误: backend/.env 缺少或为空: $k" >&2; exit 1; }
done
curl -sf -o /dev/null --max-time 3 http://localhost:8005/docs \
    || { echo "错误: 宿主机 mock :8005 未启动，请先: backend/venv/bin/python mock/app.py" >&2; exit 1; }

# 从宿主机当前构建提取哈希 js 文件名，供 smoke 断言包内前端新鲜度
EXPECTED_ASSET="$(grep -oE 'assets/index-[^"]+\.js' "$ROOT_DIR/frontend/dist/index.html" | head -1 | sed 's|assets/||')"
export EXPECTED_ASSET
if [ -n "$EXPECTED_ASSET" ]; then
    echo "前端新鲜度断言资产: $EXPECTED_ASSET"
else
    echo "提示: 未能从 frontend/dist/index.html 提取哈希资产，smoke 将跳过前端新鲜度断言"
fi

docker run --rm -i --platform "$VERIFY_PLATFORM" \
    -e LLM_BASE_URL -e LLM_API_KEY -e LLM_MODEL \
    -e EXPECTED_ASSET \
    -v "$PKG":/pkg/package.tar.gz:ro \
    -v "$V3_DIR/smoke.py":/smoke.py:ro \
    debian:buster-slim bash -s <<'STAGE2'
set -euo pipefail
cd /tmp
tar -xzf /pkg/package.tar.gz
cd activity-analysis-assistant
cat > backend/.env <<EOF
LLM_BASE_URL=$LLM_BASE_URL
LLM_API_KEY=$LLM_API_KEY
LLM_MODEL=$LLM_MODEL
LLM_TIMEOUT_SECONDS=1200
BANK_MARKETING_ACTIVITY_LIST_URL=http://host.docker.internal:8005/api2/campaigns/search
BANK_MARKETING_TEMPLATE_LIST_URL=http://host.docker.internal:8005/api2/templates
BANK_MARKETING_COMPONENT_VALUES_URL=http://host.docker.internal:8005/api2/component-values
BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL=http://host.docker.internal:8005/api2/dataservice/query/{trade_code}
EOF
export INPUT_START_OPS=n
nohup bash deploy-offline.sh </dev/null >/tmp/deploy.log 2>&1 &
READY=0
for _ in $(seq 1 120); do
    if backend/venv/bin/python -c \
        "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/activity/health', timeout=2).status==200 else 1)" \
        2>/dev/null; then
        READY=1; break
    fi
    sleep 5
done
if [ "$READY" != "1" ]; then
    echo "错误: 服务 10 分钟内未就绪，deploy.log 尾部:" >&2
    tail -50 /tmp/deploy.log >&2
    exit 1
fi
echo "服务已就绪，开始冒烟"
backend/venv/bin/python /smoke.py
STAGE2
echo "阶段 2 通过: 部署 + 启动 + 业务冒烟"
echo ""
echo "VERIFY-PASS: $PKG"

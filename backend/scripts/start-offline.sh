#!/usr/bin/env bash
#
# start-offline.sh — 全离线环境启动脚本 (麒麟 V10 ky10 x86_64 / arm64)
#
# 与 start.sh 的区别:
#   - 不依赖目标机预装的系统 Python
#   - 使用部署包内自带的便携版 Python (offline-bundle/python，架构随包)
#   - 从 offline-bundle/wheels 离线安装依赖 (不联网)
#
# 目录约定 (解压后):
#   <部署根>/
#   ├── backend/                 后端源码 (含 src/static 前端产物)
#   │   └── scripts/start-offline.sh   <- 本脚本
#   └── offline-bundle/
#       ├── python/cpython-*.tar.gz    便携版 Python
#       └── wheels/*.whl               离线依赖包
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ROOT_DIR="$(cd "$BACKEND_DIR/.." && pwd)"
BUNDLE_DIR="$ROOT_DIR/offline-bundle"
PY_HOME="$BUNDLE_DIR/python/python"   # 解压后的便携 Python 根目录

echo "============================================"
echo "  活动分析助手 - 全离线部署"
echo "  (麒麟 V10 ky10 / $(uname -m) / 便携 Python)"
echo "============================================"
echo "部署根目录: $ROOT_DIR"
echo ""

# 1. 准备便携 Python
echo ">>> [1/7] 准备便携 Python..."
if [ ! -x "$PY_HOME/bin/python3" ]; then
    TARBALL="$(ls "$BUNDLE_DIR"/python/cpython-*.tar.gz 2>/dev/null | head -1 || true)"
    if [ -z "$TARBALL" ]; then
        echo "错误: 未找到便携 Python 压缩包 ($BUNDLE_DIR/python/cpython-*.tar.gz)"
        exit 1
    fi
    echo "解压便携 Python: $(basename "$TARBALL")"
    tar -xzf "$TARBALL" -C "$BUNDLE_DIR/python"
    # python-build-standalone 解压出的目录名为 python/
fi
PYTHON="$PY_HOME/bin/python3"
echo "Python: $("$PYTHON" --version 2>&1)  ($PYTHON)"
echo ""

# 2. 创建虚拟环境 (基于便携 Python)
echo ">>> [2/7] 创建虚拟环境..."
VENV_DIR="$BACKEND_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON" -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
echo ""

# 3. 离线安装依赖
echo ">>> [3/7] 离线安装 Python 依赖..."
REQ_FILE="$BACKEND_DIR/requirements-offline.txt"
[ -f "$REQ_FILE" ] || REQ_FILE="$BACKEND_DIR/requirements.txt"
if [ -d "$BUNDLE_DIR/wheels" ] && ls "$BUNDLE_DIR/wheels"/*.whl >/dev/null 2>&1; then
    REQUIREMENTS_HASH="$("$PYTHON" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$REQ_FILE")"
    INSTALL_MARKER="$VENV_DIR/.offline-requirements.sha256"
    INSTALLED_HASH="$(cat "$INSTALL_MARKER" 2>/dev/null || true)"
    if [ "$INSTALLED_HASH" = "$REQUIREMENTS_HASH" ]; then
        echo "依赖未变化，跳过重复安装"
    else
        echo "从离线 wheels 安装 (使用 $(basename "$REQ_FILE"))..."
        pip install --no-index --find-links="$BUNDLE_DIR/wheels" -r "$REQ_FILE"
        printf '%s\n' "$REQUIREMENTS_HASH" > "$INSTALL_MARKER"
    fi
else
    echo "错误: 未找到离线 wheels ($BUNDLE_DIR/wheels), 无法离线安装"
    exit 1
fi
echo ""

# 系统 CA 不全的环境（最小化容器/定制 OS）下 openjiuwen 严格 SSL 校验会失败；
# 已有 SSL_CERT_FILE 或 certifi 不可用时保持原样，均不兜底
if [ -z "${SSL_CERT_FILE:-}" ]; then
    SSL_CERT_FILE="$(python -c 'import certifi; print(certifi.where())' 2>/dev/null || true)"
    [ -n "$SSL_CERT_FILE" ] && export SSL_CERT_FILE
fi

# 4. 配置 LLM (复用交互式引导逻辑)
echo ">>> [4/7] 配置内网 LLM..."
ENV_FILE="$BACKEND_DIR/.env"
ENV_EXAMPLE="$BACKEND_DIR/.env.example"
NEED_CONFIGURE=false

if [ ! -f "$ENV_FILE" ]; then
    [ -f "$ENV_EXAMPLE" ] && cp "$ENV_EXAMPLE" "$ENV_FILE" || touch "$ENV_FILE"
    NEED_CONFIGURE=true
else
    LLM_URL=$(grep -E '^LLM_BASE_URL=' "$ENV_FILE" | cut -d'=' -f2- | tr -d ' ' || true)
    LLM_MODEL_V=$(grep -E '^LLM_MODEL=' "$ENV_FILE" | cut -d'=' -f2- | cut -d'#' -f1 | tr -d ' ' || true)
    { [ -z "$LLM_URL" ] || [ "$LLM_URL" = "http://your-llm-host:port/v1" ]; } && NEED_CONFIGURE=true
    { [ -z "$LLM_MODEL_V" ] || [ "$LLM_MODEL_V" = "your-model-name" ]; } && NEED_CONFIGURE=true
fi

if [ "$NEED_CONFIGURE" = true ]; then
    echo ""
    echo "══════════════════════════════════════════════"
    echo "  未检测到有效的 LLM 配置, 请填写内网大模型信息"
    echo "══════════════════════════════════════════════"
    echo "示例:  vLLM: http://192.168.1.100:8000/v1   Ollama: http://192.168.1.100:11434/v1"
    echo ""
    read -r -p "内网 LLM 服务地址: " INPUT_URL
    read -r -p "模型名称: " INPUT_MODEL
    read -r -p "API Key (如不需要可留空): " INPUT_KEY
    INPUT_URL=$(echo "$INPUT_URL" | sed -E 's/\/$//')
    if [ -z "$INPUT_URL" ] || [ -z "$INPUT_MODEL" ]; then
        echo "错误: LLM 服务地址和模型名称不能为空, 请重新运行"
        exit 1
    fi
    grep -q '^LLM_BASE_URL=' "$ENV_FILE" 2>/dev/null \
        && sed -i.bak "s|^LLM_BASE_URL=.*|LLM_BASE_URL=${INPUT_URL}|" "$ENV_FILE" \
        || echo "LLM_BASE_URL=${INPUT_URL}" >> "$ENV_FILE"
    grep -q '^LLM_MODEL=' "$ENV_FILE" 2>/dev/null \
        && sed -i.bak "s|^LLM_MODEL=.*|LLM_MODEL=${INPUT_MODEL}|" "$ENV_FILE" \
        || echo "LLM_MODEL=${INPUT_MODEL}" >> "$ENV_FILE"
    if [ -n "$INPUT_KEY" ]; then
        grep -q '^LLM_API_KEY=' "$ENV_FILE" 2>/dev/null \
            && sed -i.bak "s|^LLM_API_KEY=.*|LLM_API_KEY=${INPUT_KEY}|" "$ENV_FILE" \
            || echo "LLM_API_KEY=${INPUT_KEY}" >> "$ENV_FILE"
    fi
    rm -f "$ENV_FILE.bak"
    echo "配置已写入: $ENV_FILE"
fi

mkdir -p "$BACKEND_DIR/data/uploads" "$BACKEND_DIR/data/outputs"

echo ""
echo "────────────────────────────────────────────"
echo "  当前 LLM 配置:"
grep -E '^LLM_(API_KEY|BASE_URL|MODEL)=' "$ENV_FILE" | while read -r line; do
    key=$(echo "$line" | cut -d'=' -f1); val=$(echo "$line" | cut -d'=' -f2-)
    [ "$key" = "LLM_API_KEY" ] && [ -n "$val" ] && val="${val:0:8}****"
    echo "  $key=$val"
done
echo "────────────────────────────────────────────"
echo ""

# 5. 配置银行营销外部 API
echo ">>> [5/7] 配置银行营销外部 API..."
NEED_BANK_API_CONFIGURE=false
BANK_API_KEYS=(
    BANK_MARKETING_ACTIVITY_LIST_URL
    BANK_MARKETING_TEMPLATE_LIST_URL
    BANK_MARKETING_COMPONENT_VALUES_URL
    BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL
)

for key in "${BANK_API_KEYS[@]}"; do
    value=$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2- | sed -E 's/[[:space:]]*#.*$//' | sed -E 's/^[[:space:]]+|[[:space:]]+$//g' || true)
    if [ -z "$value" ] || echo "$value" | grep -q "localhost"; then
        NEED_BANK_API_CONFIGURE=true
        break
    fi
done

if [ "$NEED_BANK_API_CONFIGURE" = true ]; then
    echo ""
    echo "══════════════════════════════════════════════"
    echo "  未检测到有效的银行营销外部 API 配置"
    echo "  生产环境必须改为目标机可达的内网真实地址"
    echo "══════════════════════════════════════════════"
    echo "示例: http://10.0.0.50:8005/api2/campaigns/search"
    echo "      http://10.0.0.50:8005/api2/templates"
    echo "      http://10.0.0.50:8005/api2/component-values"
    echo "      http://10.0.0.50:8005/api2/dataservice/query/{trade_code}"
    echo ""
    read -r -p "活动列表接口地址: " INPUT_ACTIVITY_URL
    read -r -p "模板列表接口地址: " INPUT_TEMPLATE_URL
    read -r -p "组件数值接口地址: " INPUT_COMPONENT_URL
    read -r -p "外呼活动数据接口地址: " INPUT_OUTBOUND_URL

    set_env_value() {
        local key="$1"
        local value="$2"
        if [ -n "$value" ]; then
            grep -q "^${key}=" "$ENV_FILE" 2>/dev/null \
                && sed -i.bak "s|^${key}=.*|${key}=${value}|" "$ENV_FILE" \
                || echo "${key}=${value}" >> "$ENV_FILE"
        fi
    }

    set_env_value BANK_MARKETING_ACTIVITY_LIST_URL "$INPUT_ACTIVITY_URL"
    set_env_value BANK_MARKETING_TEMPLATE_LIST_URL "$INPUT_TEMPLATE_URL"
    set_env_value BANK_MARKETING_COMPONENT_VALUES_URL "$INPUT_COMPONENT_URL"
    set_env_value BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL "$INPUT_OUTBOUND_URL"
    rm -f "$ENV_FILE.bak"
    echo "外部 API 配置已写入: $ENV_FILE"
fi

echo ""
echo "────────────────────────────────────────────"
echo "  当前银行营销外部 API 配置:"
grep -E '^BANK_MARKETING_(ACTIVITY_LIST_URL|TEMPLATE_LIST_URL|COMPONENT_VALUES_URL|OUTBOUND_ACTIVITY_DATA_URL)=' "$ENV_FILE" | while read -r line; do
    echo "  $line"
done
echo "────────────────────────────────────────────"
echo ""

# 6. 部署数据库
echo ">>> [6/7] 部署数据库..."
bash "$SCRIPT_DIR/migrate-db.sh" auto
echo ""

# 7. 启动服务
echo ">>> [7/7] 启动服务..."
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
echo "访问地址: http://<本机IP>:$PORT"
echo ""

# 可选启动运维助手 ops-assistant（失败不影响主应用）
if [ -f "$ROOT_DIR/ops/server.sh" ]; then
    [ -t 0 ] || INPUT_START_OPS=${INPUT_START_OPS:-Y}
    read -r -p "是否启动运维助手 ops-assistant? [Y/n]: " INPUT_START_OPS || true
    if [[ ! "${INPUT_START_OPS:-Y}" =~ ^[Nn]$ ]]; then
        bash "$ROOT_DIR/ops/server.sh" start || echo "ops-assistant 启动失败，不影响主应用"
    fi
fi

cd "$BACKEND_DIR"
python -m uvicorn src.main:app --host "$HOST" --port "$PORT" --log-level info

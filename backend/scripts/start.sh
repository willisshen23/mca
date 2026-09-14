#!/usr/bin/env bash
#
# start.sh — 离线环境部署启动脚本
# 在目标机器（无网络）上运行
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================"
echo "  活动分析助手 - 离线部署"
echo "============================================"
echo "部署目录: $BACKEND_DIR"
echo ""

# 1. 检查 Python
echo ">>> [1/6] 检查 Python 环境..."
PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "错误: 未找到 Python 3.10+，请手动安装"
    exit 1
fi
PY_VER=$("$PYTHON" --version 2>&1)
echo "Python: $PY_VER"
echo ""

# 2. 创建虚拟环境
echo ">>> [2/6] 创建虚拟环境..."
VENV_DIR="$BACKEND_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON" -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
echo ""

# 3. 安装依赖
echo ">>> [3/6] 安装 Python 依赖..."
USE_OFFLINE=false
if [ -d "$BACKEND_DIR/wheels" ] && ls "$BACKEND_DIR/wheels"/*.whl &>/dev/null 2>&1; then
    # wheels/ 按目标平台构建（如 Linux aarch64 靶机）；平台不匹配时离线安装会
    # 报 "No matching distribution"，回落在线安装
    OS_TAG=""
    case "$(uname -s)" in
        Linux)  OS_TAG="manylinux" ;;
        Darwin) OS_TAG="macosx" ;;
    esac
    if [ -n "$OS_TAG" ] && ls "$BACKEND_DIR/wheels"/*"$OS_TAG"*.whl &>/dev/null 2>&1; then
        USE_OFFLINE=true
    fi
fi
if [ "$USE_OFFLINE" = "true" ]; then
    echo "从离线 wheels 安装..."
    pip install --no-index --find-links="$BACKEND_DIR/wheels" \
        -r "$BACKEND_DIR/requirements.txt"
else
    echo "wheels 目录为空、不存在或平台不匹配，尝试在线安装..."
    pip install -r "$BACKEND_DIR/requirements.txt"
fi
echo ""

# 4. 配置 LLM
echo ">>> [4/6] 配置内网 LLM..."

ENV_FILE="$BACKEND_DIR/.env"
ENV_EXAMPLE="$BACKEND_DIR/.env.example"
NEED_CONFIGURE=false

if [ ! -f "$ENV_FILE" ]; then
    # 没有 .env，需要创建
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
    else
        touch "$ENV_FILE"
    fi
    NEED_CONFIGURE=true
else
    # 检查配置值是否为占位符
    LLM_URL=$(grep -E '^LLM_BASE_URL=' "$ENV_FILE" | cut -d'=' -f2- | tr -d ' ')
    LLM_MODEL=$(grep -E '^LLM_MODEL=' "$ENV_FILE" | cut -d'=' -f2- | cut -d'#' -f1 | tr -d ' ')
    if [ -z "$LLM_URL" ] || [ "$LLM_URL" = "http://your-llm-host:port/v1" ] || [ "$LLM_URL" = "http://your-llm-host:port/v1" ]; then
        NEED_CONFIGURE=true
    fi
    if [ -z "$LLM_MODEL" ] || [ "$LLM_MODEL" = "your-model-name" ]; then
        NEED_CONFIGURE=true
    fi
fi

if [ "$NEED_CONFIGURE" = true ]; then
    echo ""
    echo "══════════════════════════════════════════════"
    echo "  未检测到有效的 LLM 配置，请填写内网大模型信息"
    echo "══════════════════════════════════════════════"
    echo ""
    echo "常见场景示例:"
    echo "  Ollama:     http://192.168.1.100:11434/v1"
    echo "  vLLM:       http://192.168.1.100:8000/v1"
    echo "  LocalAI:    http://192.168.1.100:8080/v1"
    echo ""
    read -r -p "内网 LLM 服务地址 (如 http://192.168.1.100:11434/v1): " INPUT_URL
    read -r -p "模型名称 (如 qwen2.5:14b): " INPUT_MODEL
    read -r -p "API Key (如不需要可留空): " INPUT_KEY

    INPUT_URL=$(echo "$INPUT_URL" | sed -E 's/\/$//')
    if [ -z "$INPUT_URL" ] || [ -z "$INPUT_MODEL" ]; then
        echo ""
        echo "错误: LLM 服务地址和模型名称不能为空"
        echo "请重新运行: bash scripts/start.sh"
        exit 1
    fi

    # 写入 .env 配置
    if grep -q '^LLM_BASE_URL=' "$ENV_FILE" 2>/dev/null; then
        sed -i.bak "s|^LLM_BASE_URL=.*|LLM_BASE_URL=${INPUT_URL}|" "$ENV_FILE"
    else
        echo "LLM_BASE_URL=${INPUT_URL}" >> "$ENV_FILE"
    fi
    if grep -q '^LLM_MODEL=' "$ENV_FILE" 2>/dev/null; then
        sed -i.bak "s|^LLM_MODEL=.*|LLM_MODEL=${INPUT_MODEL}|" "$ENV_FILE"
    else
        echo "LLM_MODEL=${INPUT_MODEL}" >> "$ENV_FILE"
    fi
    if [ -n "$INPUT_KEY" ]; then
        if grep -q '^LLM_API_KEY=' "$ENV_FILE" 2>/dev/null; then
            sed -i.bak "s|^LLM_API_KEY=.*|LLM_API_KEY=${INPUT_KEY}|" "$ENV_FILE"
        else
            echo "LLM_API_KEY=${INPUT_KEY}" >> "$ENV_FILE"
        fi
    fi
    rm -f "$ENV_FILE.bak"
    echo ""
    echo "配置已写入: $ENV_FILE"
fi

# 确保数据目录存在
mkdir -p "$BACKEND_DIR/data/uploads" "$BACKEND_DIR/data/outputs"

echo ""
echo "────────────────────────────────────────────"
echo "  当前 LLM 配置:"
grep -E '^LLM_(API_KEY|BASE_URL|MODEL)=' "$ENV_FILE" | while read -r line; do
    key=$(echo "$line" | cut -d'=' -f1)
    val=$(echo "$line" | cut -d'=' -f2-)
    if [ "$key" = "LLM_API_KEY" ] && [ -n "$val" ]; then
        val="${val:0:8}****"
    fi
    echo "  $key=$val"
done
echo "────────────────────────────────────────────"
echo ""

# 5. 部署数据库
echo ">>> [5/6] 部署数据库..."
bash "$SCRIPT_DIR/migrate-db.sh" auto
echo ""

# 6. 启动服务
echo ">>> [6/6] 启动服务..."
echo "访问地址: http://localhost:8000"
echo "API 文档: http://localhost:8000/docs"
echo ""

python -m uvicorn src.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info

#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$DEPLOY_DIR/../.." && pwd)"
COMPOSE_FILE="$DEPLOY_DIR/docker-compose.yml"
ENV_FILE="$PROJECT_ROOT/backend/.env"
ENV_EXAMPLE="$PROJECT_ROOT/backend/.env.example"
ACTION="${1:-up}"
PROJECT_NAME="njbank-activity-analysis"

die() {
    printf '错误: %s\n' "$*" >&2
    exit 1
}

command -v docker >/dev/null 2>&1 || die "未安装 Docker"
docker info >/dev/null 2>&1 || die "Docker 服务未启动或当前用户无权访问"

if docker compose version >/dev/null 2>&1; then
    COMPOSE_COMMAND=(docker compose)
elif command -v docker-compose >/dev/null 2>&1 \
    && docker-compose version >/dev/null 2>&1; then
    COMPOSE_COMMAND=(docker-compose)
else
    die "未找到 Docker Compose（支持 docker compose 或 docker-compose）"
fi

run_compose() {
    (
        cd "$DEPLOY_DIR"
        "${COMPOSE_COMMAND[@]}" \
            --env-file "$ENV_FILE" \
            -p "$PROJECT_NAME" \
            -f "$COMPOSE_FILE" \
            "$@"
    )
}

replace_legacy_mock_url() {
    local key="$1"
    local old_value="$2"
    local new_value="$3"
    local current_value
    current_value="$(sed -n "s|^${key}=||p" "$ENV_FILE" | tail -1)"
    if [ "$current_value" = "$old_value" ]; then
        sed -i.bak "s|^${key}=.*|${key}=${new_value}|" "$ENV_FILE"
        MOCK_CONFIG_UPDATED=true
    fi
}

if [ ! -f "$ENV_FILE" ]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo "已创建配置文件: $ENV_FILE"
    echo "请按部署环境修改模型和银行接口地址；当前先使用示例配置启动。"
fi

MOCK_CONFIG_UPDATED=false
replace_legacy_mock_url \
    BANK_MARKETING_ACTIVITY_LIST_URL \
    "http://host.docker.internal:8005/api2/campaigns/search" \
    "http://mock:8005/api2/campaigns/search"
replace_legacy_mock_url \
    BANK_MARKETING_ACTIVITY_LIST_URL \
    "http://localhost:8005/api2/campaigns/search" \
    "http://mock:8005/api2/campaigns/search"
replace_legacy_mock_url \
    BANK_MARKETING_TEMPLATE_LIST_URL \
    "http://host.docker.internal:8005/api2/templates" \
    "http://mock:8005/api2/templates"
replace_legacy_mock_url \
    BANK_MARKETING_TEMPLATE_LIST_URL \
    "http://localhost:8005/api2/templates" \
    "http://mock:8005/api2/templates"
replace_legacy_mock_url \
    BANK_MARKETING_COMPONENT_VALUES_URL \
    "http://host.docker.internal:8005/api2/component-values" \
    "http://mock:8005/api2/component-values"
replace_legacy_mock_url \
    BANK_MARKETING_COMPONENT_VALUES_URL \
    "http://localhost:8005/api2/component-values" \
    "http://mock:8005/api2/component-values"
replace_legacy_mock_url \
    BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL \
    "http://host.docker.internal:8005/api2/dataservice/query/{trade_code}" \
    "http://mock:8005/api2/dataservice/query/{trade_code}"
replace_legacy_mock_url \
    BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL \
    "http://localhost:8005/api2/dataservice/query/{trade_code}" \
    "http://mock:8005/api2/dataservice/query/{trade_code}"
rm -f "$ENV_FILE.bak"
if [ "$MOCK_CONFIG_UPDATED" = true ]; then
    echo "已将旧版宿主机 Mock 地址更新为 Compose 内部地址: http://mock:8005"
fi

# ── LLM API Key 密文（enc:v1:）主密钥预检 ──
if grep -q "enc:v1:" "$ENV_FILE" 2>/dev/null; then
    if grep -q "^LLM_MASTER_KEY=" "$ENV_FILE"; then
        echo "警告: backend/.env 中检测到 LLM_MASTER_KEY——主密钥与密文同文件存放，失去加密意义，建议移除并改用宿主机环境变量注入。" >&2
    fi
    if [ -z "${LLM_MASTER_KEY:-}" ]; then
        die "backend/.env 含 enc:v1: 密文，但宿主机未提供主密钥 LLM_MASTER_KEY。

请先设置环境变量再重新执行：
    export LLM_MASTER_KEY=<hex64 字符>

主密钥由宿主机注入（compose 通过 environment 传入容器），
不要写进 backend/.env 与密文同文件。"
    fi
fi

mkdir -p "$DEPLOY_DIR/runtime-data"

case "$ACTION" in
    up|up-no-build)
        echo "使用 Compose 命令: ${COMPOSE_COMMAND[*]}"
        if [ "$ACTION" = "up-no-build" ]; then
            # 离线/内网环境：镜像已通过 docker load 导入，跳过 --build，
            # 避免 BuildKit 联网拉取基础镜像与 dockerfile 解析器。
            run_compose up -d
        else
            run_compose up -d --build
        fi
        APP_PORT="$(sed -n 's/^PORT=//p' "$ENV_FILE" | tail -1 | tr -d "\"'[:space:]")"
        APP_PORT="${APP_PORT:-9111}"
        echo ""
        echo "部署完成: http://localhost:$APP_PORT"
        echo "查看状态: bash deploy/docker/docker-deploy.sh status"
        echo "查看日志: bash deploy/docker/docker-deploy.sh logs"
        ;;
    down)
        run_compose down
        ;;
    restart)
        run_compose restart
        ;;
    logs)
        run_compose logs -f --tail=200
        ;;
    status)
        run_compose ps
        ;;
    *)
        die "不支持的操作: $ACTION（可选 up、up-no-build、down、restart、logs、status）"
        ;;
esac

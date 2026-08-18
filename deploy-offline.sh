#!/usr/bin/env bash
#
# 离线目标机唯一部署入口：
#   bash deploy-offline.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
MANIFEST="$ROOT_DIR/offline-bundle/MANIFEST.sha256"

echo "============================================"
echo "  活动分析助手 - 一键离线部署"
echo "============================================"

if [ -f "$MANIFEST" ]; then
    echo ">>> 校验离线部署包完整性"
    if command -v sha256sum >/dev/null 2>&1; then
        (
            cd "$ROOT_DIR/offline-bundle"
            sha256sum -c MANIFEST.sha256 --quiet
        )
    elif command -v shasum >/dev/null 2>&1; then
        (
            cd "$ROOT_DIR/offline-bundle"
            shasum -a 256 -c MANIFEST.sha256 >/dev/null
        )
    else
        echo "错误: 系统缺少 sha256sum/shasum，无法校验部署包" >&2
        exit 1
    fi
    echo "离线部署包校验通过"
else
    echo "警告: 未找到完整性校验清单 $MANIFEST"
fi

exec bash "$ROOT_DIR/backend/scripts/start-offline.sh"

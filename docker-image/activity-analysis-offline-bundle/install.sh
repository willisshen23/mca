#!/usr/bin/env bash
# 内网服务器一键安装：校验并导入镜像，然后启动。
set -euo pipefail
cd "$(dirname "$0")"

command -v docker >/dev/null 2>&1 || { echo "错误: 未安装 Docker" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "错误: Docker 服务未启动" >&2; exit 1; }

cd offline-dist
sha256sum -c MANIFEST.sha256
gunzip -c activity-analysis-image-arm64.tar.gz | docker load
gunzip -c activity-analysis-mock-image-arm64.tar.gz | docker load
cd ..

# Compose 编排引用的是不带架构后缀的 latest 标签，导入后回标
docker tag activity-analysis:latest-arm64 activity-analysis:latest
docker tag activity-analysis-mock:latest-arm64 activity-analysis-mock:latest

bash deploy/docker/docker-deploy.sh up-no-build

PORT="$(sed -n 's/^PORT=//p' backend/.env | tail -1 | tr -d "\"'[:space:]")"
sleep 5
echo "健康检查: http://localhost:${PORT:-9111}/health"
curl -s -m 10 "http://localhost:${PORT:-9111}/health" && echo

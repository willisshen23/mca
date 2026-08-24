# syntax=docker/dockerfile:1

FROM node:20-bookworm-slim AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim-bookworm AS python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1


FROM python-base AS mock-runtime

# 构建机访问默认 PyPI 不稳定时，通过 --build-arg PIP_INDEX_URL=<镜像> 切换。
ARG PIP_INDEX_URL=""

WORKDIR /app/mock

COPY mock/requirements.txt /tmp/mock-requirements.txt
RUN if [ -n "$PIP_INDEX_URL" ]; then \
      python -m pip install --no-cache-dir --timeout 60 --retries 10 \
        -i "$PIP_INDEX_URL" -r /tmp/mock-requirements.txt; \
    else \
      python -m pip install --no-cache-dir --timeout 60 --retries 10 \
        -r /tmp/mock-requirements.txt; \
    fi

COPY mock/ /app/mock/

EXPOSE 8005

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8005", "--log-level", "info"]


FROM python-base AS runtime

# 构建机访问默认 PyPI 不稳定时，通过 --build-arg PIP_INDEX_URL=<镜像> 切换。
ARG PIP_INDEX_URL=""

WORKDIR /app/backend

COPY backend/requirements.txt /tmp/requirements.txt
RUN if [ -n "$PIP_INDEX_URL" ]; then \
      python -m pip install --no-cache-dir --timeout 60 --retries 10 \
        -i "$PIP_INDEX_URL" -r /tmp/requirements.txt; \
    else \
      python -m pip install --no-cache-dir --timeout 60 --retries 10 \
        -r /tmp/requirements.txt; \
    fi

# tiktoken 首次 get_encoding 需联网下载 BPE 词表；构建期预热进镜像，
# 避免离线部署时运行期首次调用同步阻塞到 TCP 超时（约 1 分钟）冻结事件循环。
# 构建机不通外网时跳过（|| true），运行期由 token_budget 的一次性失败记忆兜底。
ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken-cache
RUN python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" || true

COPY backend/ /app/backend/
COPY --from=frontend-builder /build/frontend/dist/ /app/backend/src/infrastructure/static/
COPY deploy/docker/docker-entrypoint.sh /usr/local/bin/njbank-entrypoint

# 数据库种子文件（可选）：由 build-offline-images.sh 在构建前生成。
# 目标机首次启动时由入口脚本拷入数据卷（只补缺失，不覆盖已有数据）。
COPY deploy/docker/seed-data/ /app/backend/seed-data/

# 防止在 Windows 工作区构建时 CRLF 导致脚本无法执行。
RUN sed -i 's/\r$//' /usr/local/bin/njbank-entrypoint \
    && chmod +x /usr/local/bin/njbank-entrypoint \
    && mkdir -p /app/backend/data/uploads \
        /app/backend/data/outputs \
        /app/backend/data/logs

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/njbank-entrypoint"]

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

WORKDIR /app/mock

COPY mock/requirements.txt /tmp/mock-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/mock-requirements.txt

COPY mock/ /app/mock/

EXPOSE 8005

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8005", "--log-level", "info"]


FROM python-base AS runtime

WORKDIR /app/backend

COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend/ /app/backend/
COPY --from=frontend-builder /build/frontend/dist/ /app/backend/src/infrastructure/static/
COPY deploy/docker/docker-entrypoint.sh /usr/local/bin/njbank-entrypoint

# 防止在 Windows 工作区构建时 CRLF 导致脚本无法执行。
RUN sed -i 's/\r$//' /usr/local/bin/njbank-entrypoint \
    && chmod +x /usr/local/bin/njbank-entrypoint \
    && mkdir -p /app/backend/data/uploads \
        /app/backend/data/outputs \
        /app/backend/data/logs

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/njbank-entrypoint"]

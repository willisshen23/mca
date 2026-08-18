# 活动分析助手 — Docker 打包部署指南

> **v3（openJiuwen）适配状态**：2026-08-12 已实测验证——镜像构建、
> `docker compose up` 起栈、API 冒烟（offline-v3/smoke.py，SMOKE-PASS）全部通过。
> 运行时已迁移至 openJiuwen（v3 为唯一运行时），镜像构建无需额外改动。
> 四个 `BANK_MARKETING_*_URL` 以 `backend/.env` 为准——`.env` 是应用唯一的
> 配置文件，Compose 不再覆盖。`docker-deploy.sh` 会自动把 `.env` 中
> `localhost:8005` / `host.docker.internal:8005` 形式的 Mock 地址改写为
> Compose 内部地址 `http://mock:8005`，开箱即用；对接真实行内接口时
> 直接修改 `backend/.env` 中这四个 URL。
>
> **从旧版环境拷贝 `.env` 时若含 `AGENT_V3_ENABLED` 键必须删除**——该键已随
> v3 迁移移除，残留会因 pydantic-settings 的 extra-forbid 校验导致应用启动失败。

本文是 Docker 部署方式的总览文档，涵盖镜像构建、一键部署、离线镜像打包导入、
配置说明、数据管理和故障排查。更细的主题另见：

- [deploy/docker/DOCKER-SQLITE-DEPLOY.md](deploy/docker/DOCKER-SQLITE-DEPLOY.md) — Docker Compose + SQLite 部署细节
- [deploy/WINDOWS11-DOCKER-OFFLINE-BUILD.md](deploy/WINDOWS11-DOCKER-OFFLINE-BUILD.md) — Windows 11 用 Docker 构建麒麟离线 tar 包
- [DEPLOY.md](DEPLOY.md) — 不使用 Docker 的离线 tar 包部署方式

## 目录

- [1. 部署架构](#1-部署架构)
- [2. Docker 资产清单](#2-docker-资产清单)
- [3. 部署前提](#3-部署前提)
- [4. 快速部署（可联网环境）](#4-快速部署可联网环境)
- [5. 离线镜像打包与导入（内网环境）](#5-离线镜像打包与导入内网环境)
- [6. 配置说明](#6-配置说明)
- [7. 数据与备份](#7-数据与备份)
- [8. 运维管理](#8-运维管理)
- [9. 更新部署](#9-更新部署)
- [10. 故障排查](#10-故障排查)

---

## 1. 部署架构

```
┌──────────────────────────────────────────────┐
│              用户浏览器                        │
│        http://服务器IP:9111（PORT 可配）       │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│  容器 app（njbank-activity-analysis）          │
│  FastAPI :8000                                │
│  ├── /api/*    openJiuwen v3 多智能体          │
│  ├── /*        前端静态文件（构建期打入镜像）    │
│  └── SQLite    业务库 + 会话状态库             │
└──────────────────┬───────────────────────────┘
                   │ Compose 内部网络 http://mock:8005
┌──────────────────▼───────────────────────────┐
│  容器 mock（njbank-activity-analysis-mock）    │
│  银行营销 Mock 接口 :8005（不暴露宿主机端口）    │
└──────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│           内网 LLM 推理服务                    │
│      (OpenAI 兼容 API，由 .env 配置)           │
└──────────────────────────────────────────────┘
```

说明：

- 前端在镜像构建阶段编译，产物打入主应用镜像，运行时不需要 Node。
- 业务数据、配置、会话状态全部使用 SQLite，**不安装、不启动 MySQL**。
- Mock 容器仅提供开发联调接口；生产环境把 `backend/.env` 中四个
  `BANK_MARKETING_*_URL` 改为容器可访问的行内真实地址即可。不需要 Mock 时
  用 `docker compose up -d app` 只起主应用（或在 compose 中删除/注释 mock 服务）。

## 2. Docker 资产清单

| 文件 | 作用 |
|------|------|
| [deploy/docker/Dockerfile](deploy/docker/Dockerfile) | 多阶段构建：`frontend-builder`（Node 20 编译前端）、`runtime`（主应用）、`mock-runtime`（Mock 接口） |
| [deploy/docker/docker-compose.yml](deploy/docker/docker-compose.yml) | 编排 app + mock 两个服务，含健康检查 |
| [deploy/docker/docker-entrypoint.sh](deploy/docker/docker-entrypoint.sh) | 容器入口：初始化数据目录并启动 uvicorn |
| [deploy/docker/docker-deploy.sh](deploy/docker/docker-deploy.sh) | Linux/macOS 一键部署脚本 |
| [deploy/docker/docker-deploy.ps1](deploy/docker/docker-deploy.ps1) | Windows 11 一键部署脚本 |
| [deploy/docker/Dockerfile.dockerignore](deploy/docker/Dockerfile.dockerignore) | 构建上下文排除规则 |

镜像构建上下文为**项目根目录**，不要在 `deploy/docker/` 内直接执行
`docker build .`。

## 3. 部署前提

| 条件 | 要求 |
|------|------|
| Docker | Docker Desktop（Windows 11/macOS）或 Docker Engine（Linux），Windows 需使用 Linux containers |
| Docker Compose | `docker compose`（新版插件）或 `docker-compose`（旧版独立程序）任一可用 |
| 磁盘空间 | >= 5GB（含基础镜像与构建缓存） |
| 内存 | >= 4GB |
| 网络 | 首次构建需访问 Node/Python 基础镜像及 npm、pip 依赖源；纯内网环境走第 5 节离线导入 |
| 端口 | 宿主机 `PORT`（默认 9111）；容器内部固定 8000 / 8005 |

## 4. 快速部署（可联网环境）

### 4.1 一键启动

Linux / macOS：

```bash
bash deploy/docker/docker-deploy.sh
```

Windows 11（项目根目录 PowerShell）：

```powershell
.\deploy\docker\docker-deploy.ps1
```

脚本会自动完成：

1. 选择 `docker compose` 或 `docker-compose`；
2. 不存在时从 `backend/.env.example` 创建 `backend/.env`；
3. 把旧版宿主机 Mock 地址自动改写为 Compose 内部地址 `http://mock:8005`；
4. 构建前端、后端与 Mock 镜像；
5. 创建 SQLite 数据目录并启动容器（异常自动重启）。

### 4.2 配置 LLM 与银行接口

编辑 `backend/.env`（Docker 部署只维护这一份配置）：

```dotenv
PORT=9111
ALLOWED_ORIGINS=http://服务器IP:9111

LLM_API_KEY=实际密钥
LLM_BASE_URL=http://模型服务地址/v1
LLM_MODEL=实际模型名称

# 使用内置 Mock（默认）
BANK_MARKETING_ACTIVITY_LIST_URL=http://mock:8005/api2/campaigns/search
BANK_MARKETING_TEMPLATE_LIST_URL=http://mock:8005/api2/templates
BANK_MARKETING_COMPONENT_VALUES_URL=http://mock:8005/api2/component-values
BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL=http://mock:8005/api2/dataservice/query/{trade_code}
```

> **LLM API Key 密文（可选，推荐）**：`LLM_API_KEY` 等 `*_LLM_API_KEY` 支持
> `enc:v1:` 密文（AES-256-GCM）。主密钥由宿主机环境变量 `LLM_MASTER_KEY`
> 注入——compose 已内置 `${LLM_MASTER_KEY:-}` 透传，**勿写入 `backend/.env`
> 与密文同文件**。`docker-deploy.sh` 检测到密文缺主密钥时会直接报错；
> 加密/校验/轮换见 `docs/LLM-API-KEY-密文配置使用文档.md`。

生产环境将四个 `BANK_MARKETING_*_URL` 换成容器可访问的行内真实地址。

修改配置后重建容器：

```bash
bash deploy/docker/docker-deploy.sh down
bash deploy/docker/docker-deploy.sh up
```

> 注意：容器内的 `127.0.0.1` 指向容器自身。访问宿主机上的服务，
> Windows/macOS 用 `host.docker.internal`，Linux 填宿主机局域网 IP。

### 4.3 验证

```bash
curl http://localhost:9111/health
# {"status":"ok"}

# 浏览器访问
open http://localhost:9111
```

## 5. 离线镜像打包与导入（内网环境）

目标机无法访问镜像仓库 / npm / pip 时，在可联网构建机上导出镜像，再拷贝到内网导入。

### 5.1 构建镜像

```bash
# 主应用镜像
docker build -f deploy/docker/Dockerfile --target runtime \
    -t njbank-activity-analysis:latest .

# Mock 接口镜像（可选，生产直连真实接口可跳过）
docker build -f deploy/docker/Dockerfile --target mock-runtime \
    -t njbank-activity-analysis-mock:latest .
```

> 构建机为 Apple Silicon（arm64）时必须加 `--platform linux/amd64`
> （目标机麒麟 ky10 为 x86_64），否则导出的镜像无法在目标机运行；
> Intel/AMD 构建机可省略该参数。

### 5.2 导出镜像

```bash
docker save njbank-activity-analysis:latest \
    | gzip > njbank-activity-analysis-image.tar.gz

docker save njbank-activity-analysis-mock:latest \
    | gzip > njbank-activity-analysis-mock-image.tar.gz

# 生成校验文件
shasum -a 256 njbank-activity-analysis-image.tar.gz \
    > njbank-activity-analysis-image.tar.gz.sha256
```

### 5.3 传输并导入

```bash
scp njbank-activity-analysis-image.tar.gz* user@目标机:/opt/
ssh user@目标机

cd /opt
sha256sum -c njbank-activity-analysis-image.tar.gz.sha256
gunzip -c njbank-activity-analysis-image.tar.gz | docker load
```

### 5.4 目标机启动

目标机仍需项目仓库中的 `docker-compose.yml`、部署脚本和 `backend/.env`
（镜像只包含应用本体，编排文件不入镜像）。建议同步整个项目的
`deploy/docker/`、`backend/.env.example`（或已配好的 `backend/.env`）：

```bash
bash deploy/docker/docker-deploy.sh up-no-build
```

`up-no-build` 与 `up` 的唯一区别是不带 `--build`：镜像已通过
`docker load` 导入，Compose 直接复用本地镜像启动。**内网环境不要用
`up`** —— 它会触发构建，BuildKit 联网拉取基础镜像和
`docker/dockerfile:1` 解析器必然失败或卡死。

也可以直接手动执行 Compose（效果相同）：

```bash
docker compose --env-file ../../backend/.env \
    -p njbank-activity-analysis -f docker-compose.yml up -d
```

## 6. 配置说明

### 6.1 端口映射

- 容器内部固定监听 `8000`；
- 宿主机访问端口由 `backend/.env` 的 `PORT` 决定（默认 9111）；
- 修改 `PORT` 后需 `down` + `up` 生效，并同步调整 `ALLOWED_ORIGINS`。

### 6.2 Docker 部署强制的环境变量

Compose 会覆盖以下值，无需（也不应）在 `.env` 中另行设置：

| 变量 | 固定值 | 说明 |
|------|--------|------|
| `BUSINESS_DATABASE_URL` | `sqlite:////app/backend/data/skills.db` | 业务库固定 SQLite |
| `DB_PATH` | `/app/backend/data/checkpoints.db` | Agent 会话状态库 |
| `DATABASE_HOST` 等 MySQL 项 | 空 | 明确禁用 MySQL |
| `UPLOAD_DIR` / `OUTPUT_DIR` / `REPORT_EXPORT_DIR` / `LOG_DIR` | `/app/backend/data/...` | 均落在挂载卷内 |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | 容器内部监听 |

### 6.3 常用可调项

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PORT` | 宿主机访问端口 | `9111` |
| `ALLOWED_ORIGINS` | 前端跨域白名单 | 需配置为实际访问地址 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | 全局 LLM 配置 | 必填 |
| `LLM_MASTER_KEY` | LLM API Key 密文（`enc:v1:`）解密主密钥，由宿主机环境变量注入 | 未设置时仅当 `.env` 无密文才可启动 |
| `SUPERVISOR_LLM_MODEL` 等 | 各 Agent 独立模型，不配则回退全局 | 回退 `LLM_MODEL` |
| `LOG_LEVEL` | 日志级别（CRITICAL/ERROR/WARNING/INFO/DEBUG/TRACE） | `INFO` |

完整变量列表见 [DEPLOY.md](DEPLOY.md) 第 5 节与 `backend/.env.example`。

## 7. 数据与备份

所有持久化内容通过卷挂载在宿主机：

```text
deploy/docker/runtime-data/
├── skills.db          业务数据、配置和会话记录
├── v3_checkpoints.db  v3（openJiuwen）会话状态
├── checkpoints.db     v2 历史文件（不再读写，可归档）
├── uploads/           用户上传文件
├── outputs/           报告导出文件
└── logs/              服务日志
```

备份（建议先停服，避免 SQLite 写入中拷贝）：

```bash
bash deploy/docker/docker-deploy.sh down
cp -r deploy/docker/runtime-data deploy/docker/runtime-data-backup-$(date +%Y%m%d)
bash deploy/docker/docker-deploy.sh up
```

恢复：停服后用备份目录覆盖 `deploy/docker/runtime-data`，再启动。

`down` 只删除容器和网络，**不会删除** `runtime-data` 中的数据。

## 8. 运维管理

```bash
# 状态 / 日志 / 重启 / 停止
bash deploy/docker/docker-deploy.sh status
bash deploy/docker/docker-deploy.sh logs
bash deploy/docker/docker-deploy.sh restart
bash deploy/docker/docker-deploy.sh down

# 单独查看 Mock 日志
cd deploy/docker
docker compose --env-file ../../backend/.env \
    -p njbank-activity-analysis -f docker-compose.yml logs -f mock
```

Windows 将命令替换为 `.\deploy\docker\docker-deploy.ps1 <action>`。

容器已配置 `restart: unless-stopped` 与 `/health` 健康检查，
异常退出会自动拉起；`docker-deploy.sh status` 可看到 health 状态。

## 9. 更新部署

```bash
git pull                                # 或复制新代码
bash deploy/docker/docker-deploy.sh up  # 重新构建镜像并替换容器
```

`deploy/docker/runtime-data` 中的 SQLite 数据和上传文件不受影响。

## 10. 故障排查

### 10.1 容器无法启动

```bash
# 查看容器日志
bash deploy/docker/docker-deploy.sh logs

# 检查端口占用
lsof -i :9111

# 确认 Docker 正常运行
docker info
```

### 10.2 健康检查一直 unhealthy

```bash
# 进容器手动探测
docker exec njbank-activity-analysis \
    python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read())"
```

常见原因是 LLM 配置缺失导致启动阻塞，检查 `backend/.env` 中
`LLM_BASE_URL` / `LLM_MODEL` 是否填写。

### 10.3 页面能打开但分析报错

- LLM 连接失败：在目标机上 `curl $LLM_BASE_URL/models` 验证连通性，
  注意地址末尾通常需要 `/v1`；
- 银行接口失败：确认四个 `BANK_MARKETING_*_URL` 指向容器**可访问**的地址
  （容器内的 `localhost` 不是宿主机）。
- 行内 LLM 为自签 / 内部 CA 的 HTTPS 时，容器内会报
  `CERTIFICATE_VERIFY_FAILED`：将 CA 证书挂入容器并导入信任库，例如
  `-v /path/ca.crt:/usr/local/share/ca-certificates/bank.crt` 后在
  entrypoint 前执行 `update-ca-certificates`，或设置 `SSL_CERT_FILE`
  指向包含该 CA 的证书 bundle。

### 10.4 Windows 构建脚本报错或行为异常

工作区在 Windows 上时，脚本可能带 CRLF 行尾。Dockerfile 已对入口脚本做
`sed -i 's/\r$//'` 处理；若自行新增 shell 脚本进镜像，需同样处理行尾。

### 10.5 前端页面 404

说明镜像构建时前端阶段失败或产物缺失。重新完整构建：

```bash
docker build --no-cache -f deploy/docker/Dockerfile \
    --target runtime -t njbank-activity-analysis:latest .
```

### 10.6 会话数据丢失

确认卷挂载生效且 SQLite 文件存在：

```bash
ls -la deploy/docker/runtime-data/
# 应有: skills.db  v3_checkpoints.db  uploads/  outputs/  logs/
# （checkpoints.db 为 v2 历史文件，不再读写，可归档）
```

# 活动分析助手 — 部署指南

> **当前运行时**：openJiuwen agent-core（v3 为唯一运行时）。本文档是部署总入口，
> 整合了 **tar 包离线部署**、**Docker 部署** 与 **LLM API Key 密文配置** 三部分内容。
>
> 麒麟 V10 (ky10) x86_64 全离线场景（目标机无系统 Python，使用便携 Python 包，
> 由 `offline-v3/` 构建）另见 [DEPLOY-OFFLINE-KYLIN.md](DEPLOY-OFFLINE-KYLIN.md) 第 0 章。
>
> **从旧版环境拷贝 `.env` 时若含 `AGENT_V3_ENABLED` 键必须删除**——该键已随
> v3 迁移移除，残留会因 pydantic-settings extra-forbid 校验导致应用启动失败。

## 目录

- [1. 系统架构](#1-系统架构)
- [2. 部署方式选择](#2-部署方式选择)
- [3. 部署前提](#3-部署前提)
- [4. 方式一：tar 包离线部署](#4-方式一tar-包离线部署)
- [5. 方式二：Docker 部署](#5-方式二docker-部署)
- [6. 配置说明（通用）](#6-配置说明通用)
- [7. LLM API Key 密文](#7-llm-api-key-密文)
- [8. 运维管理](#8-运维管理)
- [9. 数据与备份](#9-数据与备份)
- [10. 更新部署](#10-更新部署)
- [11. 故障排查](#11-故障排查)

---

## 1. 系统架构

### tar 包部署（单进程）

```
┌──────────────────────────────────────────────┐
│              用户浏览器                        │
│           http://目标机:8000                   │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│          FastAPI 服务 (:8000)                  │
│  ┌─────────────┐  ┌────────────────────────┐ │
│  │  /api/*      │  │  /* (前端静态文件)      │ │
│  │  openJiuwen  │  │  src/infrastructure/   │ │
│  │  v3 多智能体 │  │  static/index.html...  │ │
│  └─────────────┘  └────────────────────────┘ │
│  SQLite: skills.db (业务) / v3_checkpoints.db │
└───────┬──────────────────────┬───────────────┘
        │ HTTP                 │ HTTP
┌───────▼───────────┐  ┌───────▼───────────────┐
│ 银行营销业务 API    │  │   内网 LLM 推理服务     │
│ (真实接口或本机     │  │  (OpenAI 兼容 API)     │
│  Mock :8005)      │  │                       │
└───────────────────┘  └───────────────────────┘
```

### Docker 部署（app + mock 双容器）

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

共同说明：

- 前端在构建期编译（tar 方式拷入 `backend/src/infrastructure/static/`；Docker 方式
  在镜像构建阶段打入主应用镜像），由 FastAPI 直接托管，运行时不需要 Node。
- 业务数据与会话状态全部使用 SQLite，**不依赖 MySQL**（可选切换，见 6.4）。
- Mock 接口（`mock/`，`:8005`）仅用于未对接行内真实接口时的演示/联调；生产环境把
  四个 `BANK_MARKETING_*_URL` 改为真实地址即可，Docker 下可用
  `docker compose up -d app` 只起主应用。

## 2. 部署方式选择

| 场景 | 方式 | 入口 |
|------|------|------|
| 目标机有 Docker（可联网或有镜像导入渠道） | **Docker（推荐）** | 第 5 章 |
| 目标机无 Docker，有系统 Python 3.10+ | tar 包离线部署 | 第 4 章 |
| 麒麟 V10 全离线，目标机连 Python 都没有 | 便携 Python 离线包 | [DEPLOY-OFFLINE-KYLIN.md](DEPLOY-OFFLINE-KYLIN.md) |

## 3. 部署前提

### tar 包部署

| 条件 | 要求 |
|------|------|
| 操作系统 | Linux (CentOS 7+ / Ubuntu 20.04+ / 麒麟 V10) 或 macOS |
| Python | 3.10+（建议 3.12） |
| 磁盘空间 | >= 2GB（含依赖） |
| 内存 | >= 4GB |
| 内网访问 | 可访问内网 LLM 服务与银行营销业务 API（或本机 Mock） |
| 端口 | 8000（`start.sh` 固定绑定；`server.sh` 可用 `PORT` 覆盖） |

### Docker 部署

| 条件 | 要求 |
|------|------|
| Docker | Docker Desktop（Windows 11/macOS，需 Linux containers）或 Docker Engine（Linux） |
| Docker Compose | `docker compose`（新版插件）或 `docker-compose`（旧版）任一可用 |
| 磁盘空间 | >= 5GB（含基础镜像与构建缓存） |
| 内存 | >= 4GB |
| 网络 | 首次构建需访问 Node/Python 基础镜像及 npm、pip 依赖源；纯内网走 5.3 离线导入 |
| 端口 | 宿主机 `PORT`（默认 9111）；容器内部固定 8000 / 8005 |

## 4. 方式一：tar 包离线部署

### 4.1 开发机构建打包

在**有网络**的开发机上执行：

```bash
git clone <repo-url>
cd <项目目录>/backend
bash scripts/build.sh
```

脚本会依次执行：
1. 安装前端依赖（npm ci）
2. 构建前端静态文件（npm run build），并校验产物完整性
3. 复制 `frontend/dist/` → `backend/src/infrastructure/static/`
   （应用只挂载该目录；`backend/src/static/` 为历史遗留目录，不要使用）
4. 下载 Python 依赖离线包到 `backend/wheels/`
5. 打包为 `activity-analysis-assistant-YYYYMMDD-HHMMSS.tar.gz`

如果靶机 Python 版本或平台与开发机不同，通过环境变量指定：

```bash
# 靶机 Python 3.10, Linux x86_64
TARGET_PYTHON_VERSION=310 TARGET_PLATFORM=manylinux2014_x86_64 bash scripts/build.sh

# 靶机 Python 3.12, macOS arm64
TARGET_PYTHON_VERSION=312 TARGET_PLATFORM=macosx_11_0_arm64 bash scripts/build.sh
```

若未指定，自动检测开发机 Python 版本。

> 麒麟 V10 (ky10) x86_64 全离线目标机的构建请改用 `offline-v3/build.sh`
> （自带便携 Python 与全量 wheel 闭包，含断网验证），见
> [DEPLOY-OFFLINE-KYLIN.md](DEPLOY-OFFLINE-KYLIN.md) 第 0 章。

产物布局：

```
activity-analysis-assistant-YYYYMMDD-HHMMSS.tar.gz
├── backend/
│   ├── src/              # 后端源码（含 src/infrastructure/static/ 前端产物）
│   ├── wheels/           # Python 离线依赖包
│   ├── requirements.txt  # 依赖清单
│   ├── .env.example      # 配置模板
│   ├── scripts/
│   │   ├── start.sh      # 目标机启动脚本（系统 Python）
│   │   ├── migrate-db.sh # 数据库初始化/迁移（start.sh 自动调用）
│   │   ├── server.sh     # 常驻运行管理脚本（start/stop/restart/status）
│   │   └── env_secret.py # LLM API Key 密文工具
│   └── data/             # 数据目录（空）
└── frontend/
    └── package.json      # 前端依赖清单参考
```

### 4.2 目标机部署

**传输并解压：**

```bash
scp activity-analysis-assistant-*.tar.gz user@目标机:/opt/
ssh user@目标机
cd /opt && tar -xzf activity-analysis-assistant-*.tar.gz && cd backend
```

**配置 LLM：**

- **方式一（推荐）**：直接运行 `start.sh`，脚本在检测到 `.env` 未配置或包含占位值时，
  会**交互式引导**输入内网 LLM 地址、模型名称和 API Key，自动写入 `.env`。
- **方式二（手动）**：适合脚本化批量部署或高级用户。

```bash
cp .env.example .env
vim .env
```

关键配置项（填入内网大模型的实际信息）：

```env
LLM_API_KEY=            # 内网服务通常不需要 API Key，可留空
LLM_BASE_URL=http://内网LLM服务IP:端口/v1
LLM_MODEL=模型名称
```

内网常见配置示例：

```env
# Ollama 本地部署
LLM_BASE_URL=http://192.168.1.100:11434/v1
LLM_MODEL=qwen2.5:14b

# vLLM 内网部署
LLM_BASE_URL=http://192.168.1.100:8000/v1
LLM_MODEL=/models/qwen2.5-14b

# 企业内部 API（兼容 OpenAI 范式）
LLM_BASE_URL=http://10.0.0.50:8080/v1
LLM_MODEL=gpt-4
```

确认各项值：

```bash
grep -v '^#' .env | grep -v '^$'
```

**（可选）配置银行营销业务 API**：未对接行内真实接口时，`.env.example` 默认指向本机
Mock（`http://localhost:8005/...`），需另行启动 Mock 服务（见下）。对接真实接口时，
把四个 `BANK_MARKETING_*_URL` 改为目标机可达的内网地址，完整变量见 6.3。

**启动服务：**

```bash
bash scripts/start.sh
```

首次运行会：
1. 检测 Python 版本（3.10+）
2. 创建虚拟环境 `venv/`
3. 从 `wheels/` 离线安装依赖
4. 检查 `.env` 配置，未配置则**交互式引导**输入内网 LLM 信息
5. 显示当前 LLM 配置摘要（API Key 脱敏）
6. 执行 `migrate-db.sh auto` 初始化/迁移 SQLite 业务库
7. 启动 uvicorn 服务（固定 `:8000`）

**（可选）启动 Mock 银行营销接口：**

仅在未对接行内真实接口、需要演示/联调数据时启动：

```bash
# 另开一个终端
cd <部署根>/backend
source venv/bin/activate
pip install --no-index --find-links=wheels/ -r ../mock/requirements.txt  # 若 mock 依赖未含在主依赖中
python -m mock.app   # 或: cd mock && uvicorn app:app --port 8005
```

Mock 接口默认监听 `:8005`，与 `.env.example` 中的默认 `BANK_MARKETING_*_URL` 对应。

**验证：**

```bash
# API 健康检查
curl http://localhost:8000/health
# 返回: {"status":"ok"}

# 获取可用分析组件
curl http://localhost:8000/api/components
# 返回: {"components":[{"type":"overview",...}]}

# 浏览器访问
open http://localhost:8000
```

## 5. 方式二：Docker 部署

> **v3（openJiuwen）适配状态**：2026-08-12 已实测验证——镜像构建、
> `docker compose up` 起栈、API 冒烟（offline-v3/smoke.py，SMOKE-PASS）全部通过。
> 四个 `BANK_MARKETING_*_URL` 以 `backend/.env` 为准——`.env` 是应用唯一的
> 配置文件，Compose 不再覆盖。`docker-deploy.sh` 会自动把 `.env` 中
> `localhost:8005` / `host.docker.internal:8005` 形式的 Mock 地址改写为
> Compose 内部地址 `http://mock:8005`，开箱即用；对接真实行内接口时
> 直接修改 `backend/.env` 中这四个 URL。

### 5.1 Docker 资产清单

| 文件 | 作用 |
|------|------|
| [deploy/docker/Dockerfile](deploy/docker/Dockerfile) | 多阶段构建：`frontend-builder`（Node 20 编译前端）、`runtime`（主应用）、`mock-runtime`（Mock 接口） |
| [deploy/docker/docker-compose.yml](deploy/docker/docker-compose.yml) | 编排 app + mock 两个服务，含健康检查 |
| [deploy/docker/docker-entrypoint.sh](deploy/docker/docker-entrypoint.sh) | 容器入口：初始化数据目录并启动 uvicorn |
| [deploy/docker/docker-deploy.sh](deploy/docker/docker-deploy.sh) | Linux/macOS 一键部署脚本 |
| [deploy/docker/docker-deploy.ps1](deploy/docker/docker-deploy.ps1) | Windows 11 一键部署脚本 |
| [deploy/docker/Dockerfile.dockerignore](deploy/docker/Dockerfile.dockerignore) | 构建上下文排除规则 |

镜像构建上下文为**项目根目录**，不要在 `deploy/docker/` 内直接执行 `docker build .`。

### 5.2 快速部署（可联网环境）

**一键启动**，Linux / macOS：

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

**配置 LLM 与银行接口**：编辑 `backend/.env`（Docker 部署只维护这一份配置）：

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

生产环境将四个 `BANK_MARKETING_*_URL` 换成容器可访问的行内真实地址。

修改配置后重建容器：

```bash
bash deploy/docker/docker-deploy.sh down
bash deploy/docker/docker-deploy.sh up
```

> 注意：容器内的 `127.0.0.1` 指向容器自身。访问宿主机上的服务，
> Windows/macOS 用 `host.docker.internal`，Linux 填宿主机局域网 IP。

**验证：**

```bash
curl http://localhost:9111/health
# {"status":"ok"}

# 浏览器访问
open http://localhost:9111
```

### 5.3 离线镜像打包与导入（内网环境）

目标机无法访问镜像仓库 / npm / pip 时，在可联网构建机上导出镜像，再拷贝到内网导入。

**一键打包（推荐，含数据库数据）：**

```bash
bash deploy/docker/build-offline-images.sh
```

脚本自动完成：数据库快照（`backend/data/skills.db`、`v3_checkpoints.db`
经 `sqlite3 .backup` 一致性快照到 `deploy/docker/seed-data/`，打入主应用镜像
`/app/backend/seed-data/`）→ 构建两个镜像 → 导出 `offline-dist/*.tar.gz`
及 `MANIFEST.sha256`。也支持分步执行：`snapshot` / `build` / `export`。

- 构建机访问 PyPI 不稳定时默认走清华镜像，可用 `PIP_INDEX_URL=<镜像地址>` 覆盖
  （设为空则走默认源）。
- 目标机首次启动时，入口脚本自动把镜像内的种子库拷入 `runtime-data` 卷
  （**只补缺失、不覆盖**——已有运行数据不会被镜像内数据冲掉）。
- 不想带数据时删除 `deploy/docker/seed-data/*.db` 再构建即可。

以下为手动分步方式（与脚本等价）：

**构建镜像：**

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

**导出镜像：**

```bash
docker save njbank-activity-analysis:latest \
    | gzip > njbank-activity-analysis-image.tar.gz

docker save njbank-activity-analysis-mock:latest \
    | gzip > njbank-activity-analysis-mock-image.tar.gz

# 生成校验文件
shasum -a 256 njbank-activity-analysis-image.tar.gz \
    > njbank-activity-analysis-image.tar.gz.sha256
```

**传输并导入：**

```bash
scp njbank-activity-analysis-image.tar.gz* user@目标机:/opt/
ssh user@目标机

cd /opt
sha256sum -c njbank-activity-analysis-image.tar.gz.sha256
gunzip -c njbank-activity-analysis-image.tar.gz | docker load
```

**目标机启动：**

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

### 5.4 Docker 配置要点

**端口映射：**

- 容器内部固定监听 `8000`；
- 宿主机访问端口由 `backend/.env` 的 `PORT` 决定（默认 9111）；
- 修改 `PORT` 后需 `down` + `up` 生效，并同步调整 `ALLOWED_ORIGINS`。

**Docker 部署强制的环境变量**（Compose 会覆盖以下值，无需也不应在 `.env` 中另行设置）：

| 变量 | 固定值 | 说明 |
|------|--------|------|
| `BUSINESS_DATABASE_URL` | `sqlite:////app/backend/data/skills.db` | 业务库固定 SQLite |
| `DB_PATH` | `/app/backend/data/checkpoints.db` | Agent 会话状态库 |
| `DATABASE_HOST` 等 MySQL 项 | 空 | 明确禁用 MySQL |
| `UPLOAD_DIR` / `OUTPUT_DIR` / `REPORT_EXPORT_DIR` / `LOG_DIR` | `/app/backend/data/...` | 均落在挂载卷内 |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | 容器内部监听 |

## 6. 配置说明（通用）

### 6.1 环境变量完整列表

LLM 全局配置：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | 全局 LLM API Key（支持 `enc:v1:` 密文，见第 7 章） | `""`（内网服务通常不需要） |
| `LLM_BASE_URL` | 全局 LLM 服务地址 | `""`（必填，无默认值） |
| `LLM_MODEL` | 全局模型名称 | `""`（必填，无默认值） |
| `LLM_TIMEOUT_SECONDS` | LLM 单次请求超时（秒），需小于前置代理超时 | `600` |
| `LLM_MAX_TOKENS` | 模型上下文最大 tokens | `262144` |
| `LLM_OUTPUT_TOKEN_RESERVE` | 为输出预留的 tokens | `16384` |
| `LLM_VERIFY_SSL` | 是否校验 LLM 服务 SSL 证书（自签证书设 `false`） | `false` |

按 Agent 覆盖（不配则回退全局 `LLM_*`；每个 Agent 均有
`_LLM_API_KEY` / `_LLM_BASE_URL` / `_LLM_MODEL` / `_LLM_MAX_TOKENS` 四项）：

| 前缀 | Agent |
|------|-------|
| `SUPERVISOR_` | 主管 Agent |
| `DATA_ANALYSIS_` | 数据分析 Agent |
| `REPORT_GENERATION_` | 报告生成 Agent |
| `REPORT_VALIDATION_` | 报告校验 Agent |
| `FINALIZE_` | 汇总 Agent |
| `AGENT_V2_MAIN_` | v2 主推理模型（要求端点支持 tool calling） |
| `AGENT_V2_CHEAP_` | v2 轻量模型（短确认/闲聊，可选） |
| `AGENT_V2_FALLBACK_` | v2 降级备选模型（需与主模型不同才有意义） |

Agent 运行与数据存储：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `AGENT_V2_RECURSION_LIMIT` | LangGraph 单次运行最大步数（防失控循环） | `50` |
| `AGENT_V3_MAX_ITERATIONS` | v3（openJiuwen）单次运行最大迭代数 | `50` |
| `AGENT_V3_CHECKPOINTER_DB_PATH` | v3 会话状态库路径 | `data/v3_checkpoints.db` |
| `DB_PATH` | v2 历史会话库路径（**已不读写，可归档**） | `data/checkpoints.db` |
| `BUSINESS_DATABASE_URL` | 业务库连接串 | `sqlite:///data/skills.db` |
| `DATABASE_HOST` 等 | MySQL 连接项；`DATABASE_HOST` 非空时启用 MySQL | 空（默认 SQLite） |
| `UPLOAD_DIR` | 文件上传目录 | `data/uploads` |
| `OUTPUT_DIR` | 报告输出目录 | `data/outputs` |
| `REPORT_EXPORT_DIR` | 报告导出目录 | `data/outputs/exports` |
| `MAX_UPLOAD_SIZE_MB` | 上传文件大小上限（MB） | `50` |
| `REPORT_HTML_GUARD_MAX_RETRIES` | 报告 HTML 校验失败重试次数 | `1` |

服务与日志：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HOST` / `PORT` | 服务绑定地址/端口（tar 方式 `start.sh` 固定 8000，`server.sh` 读 `PORT`；Docker 方式 `PORT` 为宿主机映射端口，默认 9111） | `0.0.0.0` / `8000` |
| `ALLOWED_ORIGINS` | 前端跨域白名单，逗号分隔 | 本机开发地址 |
| `LOG_LEVEL` | 日志级别（CRITICAL/ERROR/WARNING/INFO/DEBUG/TRACE） | `INFO` |
| `LOG_TO_FILE` | 是否写日志文件（按天轮转） | `true` |
| `LOG_DIR` / `LOG_FILE` | 日志目录/基名（实际文件名带日期，如 `app-2026-08-23.log`） | `data/logs` / `app.log` |
| `LOG_FILE_BACKUP_COUNT` | 日志保留天数 | `30` |
| `BACKEND_RESTART_COMMAND` | 前端"重启后端"按钮执行的命令，支持 `{backend_dir}`、`{script}` 占位符 | `bash {script} restart` |

### 6.2 每个 Agent 独立配置模型

```env
# 全局默认
LLM_API_KEY=sk-default
LLM_BASE_URL=http://192.168.1.100:8000/v1
LLM_MODEL=qwen2.5:14b

# 主管用强推理模型（可指向另一台服务）
SUPERVISOR_LLM_BASE_URL=http://192.168.1.101:8000/v1
SUPERVISOR_LLM_MODEL=qwen2.5:32b

# 校验用小模型降成本
REPORT_VALIDATION_LLM_MODEL=qwen2.5:7b
```

不配的项自动回退到全局 `LLM_*`。

### 6.3 银行营销外部 API 配置

系统接入了行内活动业务 API，部署到生产环境时必须改为目标机可达的内网真实地址：

```env
# 可选：外部接口需要 Bearer Token 时填写
BANK_MARKETING_API_TOKEN=
BANK_MARKETING_API_TIMEOUT_SECONDS=10

# 活动列表：按 keyword/activity_type/时间范围查询活动
BANK_MARKETING_ACTIVITY_LIST_URL=http://内网IP:端口/api2/campaigns/search
BANK_MARKETING_ACTIVITY_LIST_METHOD=POST
# 活动查询来源系统：P10 运营分析平台，S05 营销大脑
BANK_MARKETING_ACTIVITY_SRC_SYS_NO=P10

# 分析模板列表：全部或按 scene 过滤
BANK_MARKETING_TEMPLATE_LIST_URL=http://内网IP:端口/api2/templates
BANK_MARKETING_TEMPLATE_LIST_METHOD=POST

# 组件数值：按 template_id/activity_ids/component_ids/metrics 取业务指标
BANK_MARKETING_COMPONENT_VALUES_URL=http://内网IP:端口/api2/component-values
BANK_MARKETING_COMPONENT_VALUES_METHOD=POST
BANK_MARKETING_DATA_TEMPLATE_MATCH_TOP_N=2

# 外呼活动数据：URL 中 {trade_code} 占位符会按交易码逐一替换
BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL=http://内网IP:端口/api2/dataservice/query/{trade_code}
BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_METHOD=POST
BANK_MARKETING_OUTBOUND_ACTIVITY_TRADE_CODES=EDW_RTL_MED_ASSET_CONVERSION,EDW_RTL_MED_PRODUCT_TRANSACTION,EDW_RTL_MED_ACTIVITY_BASE_INFO,EDW_RTL_MED_OUTBOUND_CALL_EXECUTION,EDW_RTL_MED_SOURCE_OF_PRODUCT_VALIDCALL

# 请求缺省值
BANK_MARKETING_DEFAULT_CHANNEL=MF0
BANK_MARKETING_DEFAULT_USER_ID=1011273
BANK_MARKETING_DEFAULT_ORG_NO=001
```

接口报文结构见 [docs/API接口清单.md](docs/API接口清单.md) 及
`mock/` 目录下各接口的返回报文文档。

### 6.4 业务库：SQLite（默认）或 MySQL

默认使用 SQLite（`BUSINESS_DATABASE_URL=sqlite:///data/skills.db`），无需安装数据库。
如需切换到 MySQL，配置 `DATABASE_HOST` / `DATABASE_PORT` / `DATABASE_USERNAME` /
`DATABASE_PASSWORD` / `DATABASE_NAME`（`DATABASE_HOST` 非空即启用），并先初始化：

```bash
mysql -u root -p njbank_aa < data/mysql/schema.sql
```

历史 SQLite 数据可用 `backend/scripts/export_sqlite_to_mysql.py` 迁移。

> Docker 部署固定使用 SQLite（Compose 强制），本节仅适用于 tar 包部署。

### 6.5 模型接入兼容性

服务端使用 OpenAI 兼容客户端，兼容任何实现 OpenAI API 范式的推理服务，包括但不限于：

| 推理服务 | BASE_URL 示例 |
|---------|--------------|
| Ollama | `http://localhost:11434/v1` |
| vLLM | `http://localhost:8001/v1` |
| LocalAI | `http://localhost:8080/v1` |
| 通义千问 DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| DeepSeek API | `https://api.deepseek.com/v1` |
| OpenAI API | `https://api.openai.com/v1` |

## 7. LLM API Key 密文

> 适用范围：backend 主应用（`backend/.env`）与 ops 运维助手（`ops/.env` / 复用 `backend/.env`）。
> 配套代码：`backend/src/secrets.py`、`ops/src/secrets.py`、`backend/scripts/env_secret.py`。

### 7.1 背景与方案

`backend/.env` 中的 LLM API Key（全局 `LLM_API_KEY` 及 8 个 Agent 角色 `*_LLM_API_KEY`）
原先以明文保存。密文方案将其改为**密文存储**：

- 配置文件 / 备份 / 误发文件中不再出现明文密钥；
- 明文只在进程内存中出现，解密发生在配置加载时；
- 主密钥与密文**物理分离**（不在 `.env` 同一文件、不进 git）；
- 完全兼容旧明文配置：不含 `enc:v1:` 前缀的值原样使用，无需一次性迁移。

| 项 | 说明 |
|---|---|
| 算法 | AES-256-GCM（`cryptography`，项目已钉版 `46.0.7`，离线 wheel 已含） |
| 密文格式 | `enc:v1:<base64(nonce ‖ ciphertext ‖ tag)>`（每次加密随机 nonce，防篡改） |
| 主密钥 | 32 字节（AES-256），hex 64 字符或 base64 44 字符 |
| 主密钥来源（按优先级） | ① 环境变量 `LLM_MASTER_KEY` → ② 环境变量 `LLM_MASTER_KEY_FILE` 指定文件 → ③ 默认密钥文件 `backend/data/secrets/master.key` |
| 失败策略 | 配置含密文但主密钥缺失 → 进程**启动即失败**（fail-fast），绝不把密文当明文发出 |

密文覆盖的字段（backend `Settings` 自动解密）：

```
LLM_API_KEY
SUPERVISOR_LLM_API_KEY
DATA_ANALYSIS_LLM_API_KEY
REPORT_GENERATION_LLM_API_KEY
REPORT_VALIDATION_LLM_API_KEY
FINALIZE_LLM_API_KEY
AGENT_V2_MAIN_LLM_API_KEY
AGENT_V2_CHEAP_LLM_API_KEY
AGENT_V2_FALLBACK_LLM_API_KEY
```

ops 侧仅读取 `llm_api_key`（`OPS_LLM_API_KEY` 或回退 `backend/.env` 的 `LLM_API_KEY`），
使用同一套主密钥解密，默认密钥文件取主应用目录下的 `backend/data/secrets/master.key`。

### 7.2 快速开始

所有命令在 `backend/` 目录下执行（或任意目录用 `--env` / `--key-file` 指定路径）。
工具使用项目自带依赖，无需额外安装。

**① 生成主密钥：**

```bash
cd backend
python scripts/env_secret.py init
# 输出：主密钥已写入 backend/data/secrets/master.key（chmod 600）
```

- 默认写入 `backend/data/secrets/master.key`（该目录已 gitignore）；
- 需要输出到别处：`--file /path/master.key`；仅打印不落盘：`--print`；
- **妥善保管**：主密钥是解密的唯一凭据，丢失后密文无法恢复。

**② 加密 .env：**

```bash
python scripts/env_secret.py encrypt --env .env
# 输出：.env: 加密 N 个字段，跳过已加密 M 个，明文残留 K 个
```

- 默认处理 `LLM_API_KEY` 及所有 `*_LLM_API_KEY`；已加密的字段自动跳过（可重复执行）；
- 只处理指定字段：`--fields LLM_API_KEY,SUPERVISOR_LLM_API_KEY`；
- 注释、空行、无关行原样保留。

**③ 校验：**

```bash
python scripts/env_secret.py check --env .env --require-encrypted
# 严格模式：所有目标字段必须为密文且可解密；不加 --require-encrypted 仅验证密文可解
```

**④ 启动应用**：主密钥注入（二选一）：

```bash
# 方式一：环境变量
export LLM_MASTER_KEY=<hex64 字符>
python src/main.py

# 方式二：密钥文件（默认路径即可被识别，无需额外配置）
#   backend/data/secrets/master.key 已存在时自动读取
python src/main.py
```

启动后 `get_settings()` 即得到解密后的明文密钥，业务代码零改动。

**审计查看明文（仅限受控环境）：**

```bash
python scripts/env_secret.py decrypt --env .env
# 注意：会输出真实密钥
```

### 7.3 各部署方式下的主密钥注入

核心原则：**主密钥不能写进 `backend/.env`**（与密文同文件即失去意义），需独立注入。

**Docker Compose（`deploy/docker/`）：**

Compose 通过 `env_file` 把 `backend/.env` 原样注入容器——密文随文件进入容器，没问题。
主密钥注入方式：

- compose 已内置 `${LLM_MASTER_KEY:-}` 透传：在**宿主机**设置环境变量
  `LLM_MASTER_KEY=<hex64>` 后执行 `docker-deploy.sh` 即可（**勿写入 `backend/.env`**）；或
- 把主密钥放入 `deploy/docker/secrets/master.key`（建议 `chmod 600`，该目录已被
  git 与构建上下文排除），`docker-deploy.sh` 会在环境变量未设置时自动加载；或
- 把密钥文件只读挂载进容器并设置 `LLM_MASTER_KEY_FILE` 指向挂载路径。

`docker-deploy.sh` 检测到 `.env` 含密文但缺主密钥时会直接报错。

**tar 包 / systemd 部署：**

- 主密钥放独立的 `EnvironmentFile`（权限 600），如 `/etc/njbank/master.env`，
  内容 `LLM_MASTER_KEY=...`；或
- 密钥文件 `/opt/njbank/keys/master.key`（chmod 600）+ 在 unit 文件中设置
  `Environment=LLM_MASTER_KEY_FILE=/opt/njbank/keys/master.key`；或
- 直接使用默认路径 `backend/data/secrets/master.key`（与应用同机但不同文件，已满足分离要求）；
- 与 `backend/.env` 物理分离即可。

**ops 运维助手：**

ops 读取同一份 `backend/.env` 中的 `LLM_API_KEY`（或 `ops/.env` 的 `OPS_LLM_API_KEY`），
主密钥解析规则与 backend 一致（环境变量 → `LLM_MASTER_KEY_FILE` → 主应用
`data/secrets/master.key`）。部署时给 ops 进程注入与 backend 相同的主密钥即可。

### 7.4 密钥轮换

```bash
# 用旧密钥解密、自动生成新密钥重加密（新密钥会打印出来，请安全保管）
python scripts/env_secret.py rotate --env .env \
  --old-key-file data/secrets/master.key --generate-new

# 或显式指定新旧密钥
python scripts/env_secret.py rotate --env .env \
  --old-key-file /path/old.key --new-key <hex64 新密钥>
```

轮换后需把新主密钥部署到所有运行 backend / ops 的机器，再重启服务。

### 7.5 密文故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 启动报 `MasterKeyMissingError: 配置值以 enc:v1: 开头（密文）但未找到主密钥` | 配置是密文但进程没拿到主密钥 | 设置 `LLM_MASTER_KEY` 或 `LLM_MASTER_KEY_FILE`，或确认默认密钥文件存在 |
| 启动报 `ValueError: 密文解密失败：主密钥不匹配或密文被篡改` | 主密钥不对，或密文被改动 | 核对主密钥；用 `check` 逐字段定位；必要时用 `decrypt` 对照 |
| `encrypt` 报 `缺少主密钥` | 命令行未提供密钥且环境变量/默认文件都没有 | `--key` / `--key-file` 或设置环境变量 |
| `check` 严格模式报 `仍是明文` | 目标字段还有明文残留 | 重新执行 `encrypt` |
| 轮换后旧密钥校验失败 | 正常现象，说明轮换生效 | 用新密钥部署并校验 |

### 7.6 安全边界与注意事项

- 本方案解决「静态配置泄露」（仓库、备份、误发文件），**防不住服务器被攻破**——
  那是 KMS/HSM 的范畴；
- 主密钥必须与密文物理分离，并限制文件权限（`chmod 600`）、不进 git；
- 日志与异常信息不含明文密钥（异常只报错不打印值）；
- 前端配置页（`/env-config`）编辑的是 `.env` 原始内容，密文原样往返，
  不会被意外改回明文；
- 明文配置完全兼容：未加密的环境可继续使用，不影响现有部署与单元测试。

### 7.7 扩展到其他敏感字段

CLI 已支持任意字段（`--fields`），但**运行时解密目前只接入了 `*_LLM_API_KEY`**。
如需把 `BANK_MARKETING_API_TOKEN`、`DATABASE_PASSWORD` 等也密文化：

1. `backend/src/config.py`：把字段名加入 `_API_KEY_FIELDS` 列表（validator 自动生效）；
2. `ops/src/config.py`：对相应取值处包一层 `maybe_decrypt`；
3. 用 `encrypt --fields BANK_MARKETING_API_TOKEN` 加密。

相关测试：

```bash
cd backend && pytest tests/test_secrets.py tests/test_config_secrets.py
cd ops     && pytest tests/test_secrets.py tests/test_config.py
```

覆盖：加解密往返、篡改检测、错误密钥拒绝、明文透传、密文缺主密钥 fail-fast、
轮换后旧密钥失效、ops 侧从加密 `backend/.env` 加载等。

## 8. 运维管理

### 8.1 tar 包部署

**后台运行：**

```bash
# 方式一：项目自带管理脚本（读 .env 的 HOST/PORT，日志在 data/logs/）
bash scripts/server.sh start
bash scripts/server.sh status
bash scripts/server.sh stop

# 方式二：nohup
nohup bash scripts/start.sh > logs/app.log 2>&1 &

# 方式三：systemd（推荐生产）
sudo tee /etc/systemd/system/activity-analysis-assistant.service << 'EOF'
[Unit]
Description=活动分析助手
After=network.target

[Service]
Type=simple
User=app
WorkingDirectory=/opt/backend
EnvironmentFile=/opt/backend/.env
ExecStart=/opt/backend/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable activity-analysis-assistant
sudo systemctl start activity-analysis-assistant
```

> 使用密文 API Key 时，主密钥需对服务进程可见，见 7.3。

**查看日志：**

```bash
# systemd
journalctl -u activity-analysis-assistant -f

# server.sh / nohup（应用日志按天轮转）
tail -f data/logs/app-$(date +%F).log

# server.sh 的 uvicorn 运行日志
tail -f data/logs/uvicorn.out.log
```

**优雅重启：**

```bash
sudo systemctl restart activity-analysis-assistant
# 或
bash scripts/server.sh restart
```

前端"重启后端"按钮默认执行 `backend/scripts/server.sh restart`，
部署在 systemd/docker 下时可用 `BACKEND_RESTART_COMMAND` 覆盖。

### 8.2 Docker 部署

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

## 9. 数据与备份

### tar 包部署

```bash
# 备份业务库、会话库和上传/产出文件
tar -czf backup-$(date +%Y%m%d).tar.gz \
    data/skills.db \
    data/v3_checkpoints.db \
    data/uploads/ \
    data/outputs/
# data/checkpoints.db 为 v2 历史文件，不再读写，可归档
```

### Docker 部署

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

## 10. 更新部署

### tar 包部署

```bash
# 停服
sudo systemctl stop activity-analysis-assistant

# 备份旧版本
mv /opt/backend /opt/backend.bak

# 解压新版本
cd /opt && tar -xzf activity-analysis-assistant-*.tar.gz

# 恢复配置（注意：从旧版拷贝的 .env 若含 AGENT_V3_ENABLED 必须删除）
cp /opt/backend.bak/.env /opt/backend/.env

# 恢复数据
cp /opt/backend.bak/data/skills.db /opt/backend/data/
cp /opt/backend.bak/data/v3_checkpoints.db /opt/backend/data/

# 安装依赖（如果有新依赖）
cd /opt/backend
source venv/bin/activate
pip install --no-index --find-links=wheels/ -r requirements.txt

# 数据库迁移（start.sh 也会自动执行）
bash scripts/migrate-db.sh auto

# 启动
sudo systemctl start activity-analysis-assistant
```

### Docker 部署

```bash
git pull                                # 或复制新代码
bash deploy/docker/docker-deploy.sh up  # 重新构建镜像并替换容器
```

`deploy/docker/runtime-data` 中的 SQLite 数据和上传文件不受影响。

## 11. 故障排查

### 11.1 服务无法启动

```bash
# 检查 Python 版本
python3 --version  # 需要 >= 3.10

# 检查端口占用
lsof -i :8000    # tar 部署
lsof -i :9111    # Docker 部署

# tar 部署：手动启动查看详细错误
cd /opt/backend
source venv/bin/activate
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 --log-level debug

# Docker 部署：查看容器日志
bash deploy/docker/docker-deploy.sh logs
docker info   # 确认 Docker 正常运行
```

**启动即报 pydantic ValidationError（extra inputs are not permitted）**：
`.env` 中残留了已移除的配置键，最常见的是从旧版环境拷贝来的
`AGENT_V3_ENABLED`——删除该行即可。

**启动报密文相关错误**：见 7.5。

**Docker 健康检查一直 unhealthy：**

```bash
# 进容器手动探测
docker exec njbank-activity-analysis \
    python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read())"
```

常见原因是 LLM 配置缺失导致启动阻塞，检查 `backend/.env` 中
`LLM_BASE_URL` / `LLM_MODEL` 是否填写。

### 11.2 LLM 连接失败

```bash
# 测试 LLM 服务连通性
curl http://内网LLM地址:端口/v1/models

# 检查 .env 配置（如果 BASE_URL 或 MODEL 为空，首次调用时会报错）
cat .env | grep LLM_

# tar 部署：重新运行交互式配置
rm .env && bash scripts/start.sh
```

如果看到 `connection refused` 或 HTTP 状态码错误，通常是 `LLM_BASE_URL` 地址不可达
或路径格式不对，注意末尾是否需要 `/v1`。

行内 LLM 为自签/内部 CA 的 HTTPS 时：
- 校验失败可设 `LLM_VERIFY_SSL=false`（默认即不校验）；
- openJiuwen 框架侧对 SSL 校验更严格，系统 CA 不全的环境（最小化/定制 OS）可设置
  `SSL_CERT_FILE=$(python -c 'import certifi; print(certifi.where())')`
  指向 certifi 证书包（`start-offline.sh` 已内置该兜底）；
- Docker 容器内报 `CERTIFICATE_VERIFY_FAILED`：将 CA 证书挂入容器并导入信任库，例如
  `-v /path/ca.crt:/usr/local/share/ca-certificates/bank.crt` 后在
  entrypoint 前执行 `update-ca-certificates`，或设置 `SSL_CERT_FILE`
  指向包含该 CA 的证书 bundle。

### 11.3 银行营销接口调用失败

- 确认四个 `BANK_MARKETING_*_URL` 指向**目标机/容器可达**的地址
  （Docker 容器内的 `localhost` 不是宿主机）；
- 使用 Mock 时确认 Mock 已启动：tar 部署 `curl http://localhost:8005/api2/templates`，
  Docker 部署看 mock 容器日志（8.2）；
- 接口需要鉴权时检查 `BANK_MARKETING_API_TOKEN`。

### 11.4 文件上传失败

```bash
# 确认上传目录存在且有写权限
ls -la data/uploads/     # Docker 部署为 deploy/docker/runtime-data/uploads/
chmod 755 data/uploads/
# 超过大小限制时调整 MAX_UPLOAD_SIZE_MB（默认 50MB）
```

### 11.5 前端页面 404

**tar 部署**：应用只挂载 `backend/src/infrastructure/static/`，确认该目录存在且包含
`index.html`：

```bash
ls backend/src/infrastructure/static/
# 应有: index.html  assets/
```

注意 `backend/src/static/` 是历史遗留目录，**应用不读取**，往里拷文件无效。
如缺失，在开发机上重新执行构建脚本（`backend/scripts/build.sh` 会拷到正确目录），或手动：

```bash
cd frontend && npm run build
cp -r dist ../backend/src/infrastructure/static/
```

**Docker 部署**：说明镜像构建时前端阶段失败或产物缺失，重新完整构建：

```bash
docker build --no-cache -f deploy/docker/Dockerfile \
    --target runtime -t njbank-activity-analysis:latest .
```

### 11.6 Windows 构建脚本报错或行为异常

工作区在 Windows 上时，脚本可能带 CRLF 行尾。Dockerfile 已对入口脚本做
`sed -i 's/\r$//'` 处理；若自行新增 shell 脚本进镜像，需同样处理行尾。

### 11.7 会话数据丢失

v3 会话状态库为 `v3_checkpoints.db`，业务库为 `skills.db`，确认文件存在且可读写：

```bash
# tar 部署
ls -la data/v3_checkpoints.db data/skills.db

# Docker 部署
ls -la deploy/docker/runtime-data/
# 应有: skills.db  v3_checkpoints.db  uploads/  outputs/  logs/
```

`checkpoints.db` 为 v2 历史文件，新版不再读写，不影响会话。

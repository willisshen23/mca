# 活动分析助手 — 全离线部署指南（麒麟 V10 / x86_64 / arm64）

> **【openJiuwen 版（agent_v3）部署请看这里】** 2026-08-12 起运行时迁移至 openJiuwen
> agent-core（v3 为唯一运行时）。新离线包由 `offline-v3/` 构建与验证，见本文
> [第 0 章](#0-openjiuwen-版agent_v3离线部署p4)。下文第 1-9 章为 langchain 时代
> 旧版流程，仅作历史归档保留。
>
> **2026-08-24 起支持 arm64（aarch64，鲲鹏/飞腾等麒麟 V10 机型）**：构建时设
> `TARGET_ARCH=aarch64` 即可，包名带 `-arm64` 后缀；业务代码为字节码编译后的
> pyc-only 产物（无 .py 源码）。

---

## 0. openJiuwen 版（agent_v3）离线部署（P4）

### 0.1 与旧版差异

| 项 | 旧版（langchain） | 新版（openJiuwen v3） |
|---|---|---|
| 构建脚本 | `scripts/build-offline-package.sh`（需 Linux 构建机） | `offline-v3/build.sh`（本机 Docker，linux/amd64 容器即可同时出 x86_64/arm64 包） |
| 目标架构 | 仅 x86_64 | x86_64（默认）/ arm64（`TARGET_ARCH=aarch64`） |
| 业务代码形态 | Python 源码 | pyc-only（构建期 `compileall` 编译并剥离 .py，运维脚本保留源码） |
| wheel 集 | `offline-bundle/wheels`（langchain 系，已归档） | `offline-v3/wheels`（x86_64）/ `offline-v3/wheels-aarch64`（arm64），openJiuwen 全量闭包 |
| 构建验证 | 无 | `offline-v3/verify.sh`（断网安装 + 业务冒烟，按包名自动匹配容器架构） |
| 目标机部署 | `bash deploy-offline.sh` | **不变** |

> **警示**：旧 `scripts/build-offline-package.sh` 及历史 tar 包的前端拷贝目标
> （`backend/src/static`）与应用挂载点（`backend/src/infrastructure/static`）错位，
> 历史包服务的是 git 跟踪的 2026-07-10 旧前端；归档脚本不再维护，请勿再用其出包。

目标机侧部署步骤与第 5 章完全一致（产物内部布局未变），仅三点注意：

1. **`.env` 若从旧版环境拷贝，必须删除 `AGENT_V3_ENABLED` 键**——该键已随 v3 成为
   唯一运行时而移除，残留会导致 pydantic-settings ValidationError 启动失败。
2. `data/checkpoints.db`（v2 langgraph checkpoint）为历史文件，新版不读写，可归档保留。
3. 目标机若系统 CA 证书不全（最小化/定制 OS），`start-offline.sh` 已内置
   `SSL_CERT_FILE=certifi` 兜底，无需手工处理。

部署时长提示：容器实测从解压到服务就绪约 7 分钟（venv 离线安装为主），机械硬盘目标机可能更慢，属正常现象。

### 0.2 构建（本机 macOS + Docker）

```bash
cd frontend && npm ci && npm run build && cd ..

# x86_64 目标机（默认）
docker run --rm --platform linux/amd64 -v "$PWD":/workspace -w /workspace \
  python:3.12-bookworm bash offline-v3/build.sh
# 产物: offline-v3/dist/activity-analysis-assistant-offline-amd64-<时间戳>.tar.gz

# arm64 目标机（aarch64，鲲鹏/飞腾等麒麟 V10 机型）
# wheel 下载、便携 Python、字节码编译均跨架构可行，仍在 linux/amd64 容器中构建
docker run --rm --platform linux/amd64 -e TARGET_ARCH=aarch64 \
  -v "$PWD":/workspace -w /workspace \
  python:3.12-bookworm bash offline-v3/build.sh
# 产物: offline-v3/dist/activity-analysis-assistant-offline-arm64-<时间戳>.tar.gz
```

### 0.3 构建后验证（可选但强烈建议）

```bash
# 前置: 宿主机起 mock（backend/venv/bin/python mock/app.py），backend/.env 配好 LLM
bash offline-v3/verify.sh
# 通过标准: 输出 VERIFY-PASS（阶段1=断网安装铁证闭包完备；阶段2=对话/审批/报告冒烟）
# verify.sh 按包名自动选择 linux/amd64 或 linux/arm64 容器；
# 在 x86_64 构建机上验证 arm64 包走 Docker 自带 QEMU 模拟，明显更慢属正常
```

### 0.4 目标机部署

与第 5 章一致：拷贝 tar.gz 到目标机 → `tar -xzf` → `bash deploy-offline.sh`，
按提示填写内网 LLM 与银行营销接口地址。

---

> 适用目标机：银河麒麟 V10 (ky10)，**x86_64 或 arm64（aarch64）** 架构，内核 4.19+。
> 如 `Linux uat-coapapB1 4.19.90-52.22.v2207.ky10.x86_64 ... x86_64 GNU/Linux`
> 或鲲鹏/飞腾机型的 `... ky10.aarch64 ... aarch64 GNU/Linux`。
>
> 本指南针对 **完全无外网** 的目标机，且 **目标机未预装 Python**。
> 部署包内自带 **便携版 Python 3.12**（架构随包）与全部 **Python 离线依赖（wheel）**，
> 无需在目标机编译、无需联网、无需安装系统级 Python。

---

## 目录

- [1. 方案概述](#1-方案概述)
- [2. 部署包内容](#2-部署包内容)
- [3. 目标机要求](#3-目标机要求)
- [4. 在开发机上构建部署包](#4-在开发机上构建部署包)
  - [4.1 前端构建（产物已内置，可跳过）](#41-前端构建产物已内置可跳过)
  - [4.2 下载便携 Python（x86_64-linux-gnu）](#42-下载便携-pythonx86_64-linux-gnu)
  - [4.3 下载 Python 离线依赖](#43-下载-python-离线依赖)
  - [4.4 打包（完整离线包，含 Python + wheels）](#44-打包完整离线包含-python--wheels)
  - [4.5 打包（仅代码，不含离线依赖包）](#45-打包仅代码不含离线依赖包)
- [5. 目标机离线部署](#5-目标机离线部署)
- [6. 配置说明](#6-配置说明)
- [7. 验证与访问](#7-验证与访问)
- [8. 运维管理（后台运行/日志/备份）](#8-运维管理)
- [9. 故障排查](#9-故障排查)

---

## 1. 方案概述

| 关键点 | 选择 | 说明 |
|--------|------|------|
| Python 来源 | **便携版 Python 3.12**（python-build-standalone） | 目标机无需预装 Python，解压即用 |
| Python 依赖 | **离线 wheel 包**（cp312 / manylinux x86_64，以实际目录为准） | `pip --no-index` 离线安装 |
| 前端 | **预构建静态产物** | 已打包进 `backend/src/static/`，目标机无需 Node.js |
| 系统 RPM | 无额外浏览器运行库 | 便携 Python 仅依赖 glibc≥2.17 |
| LLM | 内网 OpenAI 兼容接口 | 启动时交互式填写地址/模型/Key |

**为什么用便携版 Python？**
银河麒麟 V10 自带的系统 Python 通常为 3.7.x，低于本项目要求的 3.10+；在纯离线环境从源码编译 Python 需要 gcc 工具链和一连串 `-devel` 系统包，成本极高。`python-build-standalone` 提供面向 `x86_64-unknown-linux-gnu` 的自包含 Python 发行版，目标平台为 glibc 2.17+（manylinux2014），银河麒麟 V10（glibc 2.28）完全兼容，**解压即用、无需编译**。

```
┌─────────────────────────────────────────────┐
│              用户浏览器                       │
│        http://目标机IP:8000                   │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│   FastAPI (便携 Python 3.12 venv, :8000)      │
│   /api/*  LangGraph 多智能体                  │
│   /*      前端静态产物 (src/static)           │
└──────────────────┬──────────────────────────┘
                   │ HTTP (OpenAI 兼容)
┌──────────────────▼──────────────────────────┐
│          内网 LLM 推理服务                    │
└─────────────────────────────────────────────┘
```

---

## 2. 部署包内容

解压后的目录结构：

```
activity-analysis-assistant/
├── deploy-offline.sh              ★ 目标机唯一部署入口
├── backend/
│   ├── src/                       后端源码（含 src/static 前端产物）
│   ├── requirements.txt           完整依赖清单
│   ├── requirements-offline.txt   离线安装清单（内容与 requirements.txt 一致）★
│   ├── .env.example               配置模板
│   ├── scripts/
│   │   ├── start-offline.sh       ★ 全离线启动脚本（使用便携 Python）
│   │   ├── start.sh               原启动脚本（依赖系统 Python，本方案不用）
│   │   └── build.sh               构建脚本（开发机用）
│   └── data/                      数据目录（运行时生成）
└── offline-bundle/
    ├── python/
    │   └── cpython-3.12.13-x86_64-linux-gnu.tar.gz   ★ 便携 Python
    └── wheels/
        └── *.whl                  ★ 离线依赖包（以实际目录为准）
```

带 ★ 的是本离线方案的核心新增文件。

---

## 3. 目标机要求

| 条件 | 要求 |
|------|------|
| 操作系统 | 银河麒麟 V10 (ky10) 或同级别 glibc≥2.17 的 Linux |
| 架构 | x86_64 |
| Python | **无需预装**（部署包自带便携版） |
| 磁盘空间 | ≥ 1.5GB |
| 内存 | ≥ 4GB |
| 内网访问 | 可访问内网 LLM 服务 |
| 端口 | 8000（可改） |
| 系统库 | 仅需 glibc≥2.17（V10 默认满足） |

检查目标机 glibc 版本（应 ≥ 2.17）：

```bash
ldd --version | head -1
```

---

## 4. 在开发机上构建部署包

> 此步骤在 **联网的 Linux x86_64 构建机** 上执行，以确保便携 Python 和二进制
> wheels 与麒麟目标机的平台、架构一致。

### 4.0 一键构建（推荐）

以下一个命令会自动完成前端构建、便携 Python 准备、Python wheels 下载、
完整性清单生成和离线包打包：

```bash
bash scripts/build-offline-package.sh
```

生成文件：

```text
activity-analysis-assistant-offline-YYYYMMDD-HHMMSS.tar.gz
```

后续 4.1～4.4 是一键脚本内部步骤的拆解，仅用于排查问题，正常部署不需要逐条执行。

### 4.1 前端构建（产物已内置，可跳过）

```bash
cd frontend
npm ci
npm run build
rm -rf ../backend/src/static && cp -r dist ../backend/src/static
```

### 4.2 下载便携 Python（x86_64-linux-gnu）

```bash
mkdir -p offline-bundle/python
curl -L -o offline-bundle/python/cpython-3.12.13-x86_64-linux-gnu.tar.gz \
  "https://github.com/astral-sh/python-build-standalone/releases/download/20260623/cpython-3.12.13%2B20260623-x86_64-unknown-linux-gnu-install_only.tar.gz"
```

### 4.3 下载 Python 离线依赖（关键：跨平台下载 cp312/manylinux x86_64）

下面是排查时可单独执行的 wheel 下载命令：

```bash
# 用 Python 3.12 建一个干净的构建虚拟环境，并升级 pip
python3.12 -m venv /tmp/buildvenv
/tmp/buildvenv/bin/pip install -U pip

mkdir -p offline-bundle/wheels
/tmp/buildvenv/bin/pip download \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 \
  --platform manylinux_2_17_x86_64 \
  --platform manylinux_2_28_x86_64 \
  --python-version 312 \
  --implementation cp \
  --abi cp312 \
  -r backend/requirements-offline.txt \
  -d offline-bundle/wheels/

```

要点：
- `--platform/--python-version/--abi/--implementation` 共同锁定“目标机的 Python 3.12 + manylinux x86_64”，与开发机自身平台无关。
- `--only-binary=:all:` 确保只下载二进制 wheel（纯 Python 包以 `py3-none-any` 形式存在，仍可下载），避免目标机需要编译。
- 本项目全部依赖均有对应 wheel，下载零失败。

### 4.4 打包（完整离线包，含 Python + wheels）

```bash
tar -czf activity-analysis-assistant-offline-$(date +%Y%m%d).tar.gz \
  --exclude='backend/venv' \
  --exclude='backend/__pycache__' \
  --exclude='backend/src/**/__pycache__' \
  --exclude='backend/.env' \
  --exclude='backend/data' \
  --exclude='.git' \
  backend/ offline-bundle/
```

### 4.5 打包（仅代码，不含离线依赖包）

如果目标机已经部署过完整离线包（已有便携 Python 和 wheels），或者目标机本身就有 Python 3.12 及所需依赖，只想更新/传输代码，可使用以下脚本打包。该包**不包含 `offline-bundle/` 目录，也不包含运行时生成的 `backend/data/` 目录**，体积显著更小。

```bash
# 仅打包代码（不含 offline-bundle/ 中的便携 Python 与 wheels）
tar -czf activity-analysis-assistant-code-$(date +%Y%m%d).tar.gz \
  --exclude='backend/venv' \
  --exclude='backend/.venv' \
  --exclude='backend/.pytest_cache' \
  --exclude='backend/__pycache__' \
  --exclude='backend/src/**/__pycache__' \
  --exclude='backend/.env' \
  --exclude='backend/data' \
  --exclude='.git' \
  --exclude='offline-bundle/' \
  backend/
```

适用场景：
- 已部署过完整离线包，后续只需更新 `backend/src/` 等业务代码。
- 开发/测试环境，目标机已预装 Python 3.12 且能联网安装依赖（或已存在可用的 `backend/venv`）。
- 不需要离线便携 Python，希望减小传输包体积。

> 注意：此包解压后没有 `offline-bundle/`，因此**不能**直接使用 `scripts/start-offline.sh` 启动（该脚本依赖 `offline-bundle/python/` 和 `offline-bundle/wheels/`）。请确保目标机已存在有效的 `backend/venv` 虚拟环境，或改用系统 Python 按 `backend/requirements.txt` / `requirements-offline.txt` 安装依赖后启动。

---

## 5. 目标机离线部署

正常情况下，解压部署包后只需执行一个入口：

```bash
cd activity-analysis-assistant
bash deploy-offline.sh
```

入口会先校验离线包完整性，再自动完成 Python 解压、虚拟环境创建、离线依赖安装、
配置引导和服务启动。依赖清单没有变化时会跳过重复安装。

### 5.1 传输并解压

```bash
# 从开发机传到目标机（任意可达方式：scp / U盘 / 内网文件服务）
scp activity-analysis-assistant-offline-*.tar.gz user@目标机IP:/opt/

# 目标机上
cd /opt
tar -xzf activity-analysis-assistant-offline-*.tar.gz
cd activity-analysis-assistant
```

### 5.2 一键启动（自动解压便携 Python + 离线装依赖 + 引导配置）

```bash
bash deploy-offline.sh
```

脚本依次完成：
1. 解压便携 Python 到 `offline-bundle/python/python/`
2. 用便携 Python 创建虚拟环境 `backend/venv/`
3. 从 `offline-bundle/wheels/` **离线安装**依赖（`pip --no-index`，使用 `requirements-offline.txt`）
4. 检查 `.env`，未配置则**交互式引导**填写内网 LLM 地址/模型/Key
5. 检查 `BANK_MARKETING_*_URL`，为空或仍指向 `localhost` 时**交互式引导**填写行内活动业务 API 地址
6. 部署数据库结构
7. 启动 uvicorn 服务（默认 `0.0.0.0:8000`）

> 自定义端口/绑定地址：`PORT=9000 HOST=0.0.0.0 bash deploy-offline.sh`

---

## 6. 配置说明

### 6.1 LLM 相关环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | 全局 LLM API Key | `""`（内网通常不需要） |
| `LLM_BASE_URL` | 全局 LLM 地址 | 必填，如 `http://10.0.0.50:8000/v1` |
| `LLM_MODEL` | 全局模型名 | 必填 |
| `SUPERVISOR_LLM_MODEL` | 主管 Agent 模型 | 回退到 `LLM_MODEL` |
| `DATA_ANALYSIS_LLM_MODEL` | 数据分析 Agent 模型 | 回退到 `LLM_MODEL` |
| `REPORT_GENERATION_LLM_MODEL` | 报告生成 Agent 模型 | 回退到 `LLM_MODEL` |
| `REPORT_VALIDATION_LLM_MODEL` | 报告校验 Agent 模型 | 回退到 `LLM_MODEL` |
| `FINALIZE_LLM_MODEL` | 汇总 Agent 模型 | 回退到 `LLM_MODEL` |

> 每个 Agent 还可单独配 `*_LLM_API_KEY` / `*_LLM_BASE_URL`，不配则回退到全局。

### 6.2 系统 / 数据库 / 日志环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DB_PATH` | LangGraph checkpoint SQLite 路径 | `data/checkpoints.db` |
| `DATABASE_HOST` | 数据库 IP 地址 | 如 `127.0.0.1` |
| `DATABASE_PORT` | 数据库端口 | 如 `3306` |
| `DATABASE_USERNAME` | 数据库用户名 | MySQL 模式必填 |
| `DATABASE_PASSWORD` | 数据库密码 | 可直接填写，无需 URL 编码 |
| `DATABASE_NAME` | 数据库名 | 如 `njbank_aa` |
| `BUSINESS_DATABASE_URL` | 高级业务库连接串（SQLAlchemy） | 默认 `sqlite:///data/skills.db`，远程 MySQL 可填写完整 URL |
| `UPLOAD_DIR` | 上传目录 | `data/uploads` |
| `OUTPUT_DIR` | 输出目录 | `data/outputs` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `LOG_TO_FILE` | 是否落盘（按天轮转） | `true` |
| `LOG_DIR` / `LOG_FILE` / `LOG_FILE_BACKUP_COUNT` | 日志目录/基名/保留天数 | `data/logs` / `app.log` / `30` |
| `REPORT_HTML_GUARD_MAX_RETRIES` | 报告 HTML 校验失败后的最大重试次数 | `1` |
| `ALLOWED_ORIGINS` | CORS 允许来源（逗号分隔） | 按需配置，如 `http://前端地址:端口` |
| `BACKEND_RESTART_COMMAND` | 后端重启按钮执行的命令 | `bash {script} restart`（占位符：`{backend_dir}`、`{script}`） |
| `HOST` / `PORT` | 服务绑定地址 / 端口 | `0.0.0.0` / `8000` |

> 配置 `DATABASE_HOST`、`DATABASE_PORT`、`DATABASE_USERNAME`、
> `DATABASE_PASSWORD`、`DATABASE_NAME` 后，系统会拼接
> MySQL 连接；驱动 `pymysql`
> 已包含在离线 wheel 中，无需额外安装。
>
> 数据库部署支持 MySQL 及使用 MySQL 协议的兼容数据库。`migrate-db.sh`
> 统一调用离线虚拟环境中的 `PyMySQL` 迁移器，不检测、不调用系统
> `mysql` 命令，也无需安装系统级 MySQL 客户端。兼容数据库仍需支持
> `information_schema`、InnoDB 风格 DDL、`PREPARE/EXECUTE` 以及当前
> SQL 中使用的字符集和索引语法。

### 6.3 活动外部 API 环境变量（生产必配）

新版接入了行内活动业务 API，**这些地址必须改为目标机可达的内网真实地址**（`.env.example` 中默认是 `localhost:8005` 占位）：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `BANK_MARKETING_API_TOKEN` | 外部接口 Bearer Token（可选） | `""` |
| `BANK_MARKETING_API_TIMEOUT_SECONDS` | 请求超时 | `10` |
| `BANK_MARKETING_ACTIVITY_LIST_URL` / `_METHOD` | 活动列表接口 | `http://localhost:8005/api2/campaigns/search` / `POST` |
| `BANK_MARKETING_TEMPLATE_LIST_URL` / `_METHOD` | 模板列表接口 | `.../api2/templates` / `POST` |
| `BANK_MARKETING_COMPONENT_VALUES_URL` / `_METHOD` | 组件数值接口 | `.../api2/component-values` / `POST` |
| `BANK_MARKETING_DATA_TEMPLATE_MATCH_TOP_N` | 模板匹配返回条数 | `2` |
| `BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL` / `_METHOD` | 外呼活动查询接口（URL 含 `{trade_code}` 占位符） | `.../api2/dataservice/query/{trade_code}` / `POST` |
| `BANK_MARKETING_OUTBOUND_ACTIVITY_TRADE_CODES` | 逐一替换的交易码列表（逗号分隔） | 见 `.env.example` |
| `BANK_MARKETING_DEFAULT_CHANNEL` | 默认渠道编码 | `MF0` |
| `BANK_MARKETING_DEFAULT_USER_ID` / `_ORG_NO` | identity 默认值 | `1011273` / `001` |

### 6.4 手动配置（替代交互式）

```bash
cp .env.example .env
vim .env
```

`.env.example` 已包含上述全部分组，逐项按内网实际信息填写即可。重点确认：
1. `LLM_BASE_URL` / `LLM_MODEL`（必填）
2. `BANK_MARKETING_*_URL`（改为内网真实地址，否则相关分析会连不上）
3. 五个 `DATABASE_*` 连接字段（如用 MySQL 业务库；`DATABASE_HOST` 留空则使用 SQLite）

服务端基于 `langchain-openai` 的 `ChatOpenAI`，兼容任何 OpenAI 范式接口（vLLM / Ollama / LocalAI / 企业内部 API）。

---

## 7. 验证与访问

```bash
# 健康检查
curl http://localhost:8000/health
# {"status":"ok"}

# 可用分析组件
curl http://localhost:8000/api/components

# 浏览器访问
http://目标机IP:8000
```

确认依赖已正确离线安装：

```bash
source backend/venv/bin/activate
python -c "import fastapi, langgraph, langchain_openai, openpyxl, tiktoken, pydantic; print('deps OK')"
```

---

## 8. 运维管理

> **首次部署注意：** `deploy-offline.sh` 包含交互式 LLM 配置引导，首次部署请先在前台执行一次，完成环境初始化并生成 `.env`：
>
> ```bash
> bash deploy-offline.sh
> ```
>
> 待服务正常启动后按 `Ctrl+C` 停止，再选择下面的 systemd 或 nohup 方式后台运行。

### 8.1 后台运行（systemd，推荐）

```bash
DEPLOY=/opt/activity-analysis-assistant        # 替换为实际解压目录
sudo tee /etc/systemd/system/activity-analysis-assistant.service << EOF
[Unit]
Description=活动分析助手 (offline)
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$DEPLOY/backend
EnvironmentFile=$DEPLOY/backend/.env
ExecStart=$DEPLOY/backend/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now activity-analysis-assistant
journalctl -u activity-analysis-assistant -f
```

> 注意：venv 内的 `python` 指向便携 Python 的解释器，systemd 直接调用即可，无需 source 激活。

### 8.2 nohup 方式（无 systemd 权限时使用）

> 前提：已按本章开头说明完成首次前台配置，`.env` 已存在且有效。

```bash
cd backend
mkdir -p logs

# 使用 venv 中的便携 Python 直接启动 uvicorn
nohup venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > logs/app.log 2>&1 &

# 记录 PID，方便后续管理
echo $! > logs/app.pid

# 查看日志
tail -f logs/app.log
```

停止与查看状态：

```bash
cd backend

# 停止服务
kill "$(cat logs/app.pid)"

# 查看进程状态
ps -p "$(cat logs/app.pid)" -o pid,cmd,etime
```

### 8.3 数据备份

```bash
cd backend
tar -czf backup-$(date +%Y%m%d).tar.gz data/checkpoints.db data/uploads/ data/outputs/
```

### 8.4 没有 `nohup` 时的替代方案

银河麒麟 V10 通常已内置 `nohup`，若提示 `command not found`，可先检查：

```bash
which nohup || find /usr -name nohup 2>/dev/null
# 如找到但不在 PATH 中，可临时使用绝对路径
/usr/bin/nohup venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > logs/app.log 2>&1 &
```

确实没有 `nohup` 时，可用以下任一方式后台运行。

#### 方式一：`screen` / `tmux`（会话保持，推荐）

麒麟 V10 通常预装 `screen`，会话断开后服务仍继续运行。

```bash
# screen 方式
cd backend
screen -S activity-analysis-assistant -dm bash -c 'venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > logs/app.log 2>&1'

# 重新进入会话查看日志
screen -r activity-analysis-assistant

# 临时退出会话（服务不停止）：按 Ctrl+A, D
# 停止服务：进入会话后按 Ctrl+C
```

若安装了 `tmux`：

```bash
tmux new-session -d -s activity-analysis-assistant 'venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > logs/app.log 2>&1'

# 查看日志
tmux attach -t activity-analysis-assistant

# 退出会话（服务不停止）：按 Ctrl+B, D
# 停止服务：进入会话后按 Ctrl+C
```

#### 方式二：`setsid`（脱离终端）

```bash
cd backend
setsid venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > logs/app.log 2>&1 &
echo $! > logs/app.pid
tail -f logs/app.log
```

#### 方式三：bash 内置 `disown`

```bash
cd backend
venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000 > logs/app.log 2>&1 &
echo $! > logs/app.pid
disown

tail -f logs/app.log
```

> `disown` 后关闭终端不会终止进程，但不如 `nohup`/`screen`/`setsid` 彻底，适合临时调试。

#### 方式四：Supervisor（进程守护）

如需统一托管多个后台进程，可安装 `supervisor` 后新增配置：

```ini
; /etc/supervisord.d/activity-analysis-assistant.ini
[program:activity-analysis-assistant]
directory=/opt/activity-analysis-assistant-offline-XXXX/backend
command=/opt/activity-analysis-assistant-offline-XXXX/backend/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
environment=LOG_LEVEL="INFO"
user=your-user
autostart=true
autorestart=true
stdout_logfile=/opt/activity-analysis-assistant-offline-XXXX/backend/logs/app.log
stderr_logfile=/opt/activity-analysis-assistant-offline-XXXX/backend/logs/app.err.log
```

然后：

```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start activity-analysis-assistant
sudo supervisorctl status activity-analysis-assistant
```

---

## 9. 故障排查

### 9.1 便携 Python 无法运行

```bash
# 确认架构匹配（应为 x86_64）
uname -m

# 确认 glibc ≥ 2.17
ldd --version | head -1

# 手动测试便携 Python
offline-bundle/python/python/bin/python3 --version
```
若报 `version 'GLIBC_2.xx' not found`，说明目标机 glibc 过低，需改用更低 manylinux 基线的 Python 构建。

### 9.2 依赖安装报 “No matching distribution”

通常是 wheels 与目标 Python 版本不符。确认：
- 便携 Python 为 3.12（本包），wheel 文件名应含 `cp312`；
- 若更换了 Python 版本，需在开发机用对应 `--python-version/--abi` 重新下载 wheel。

### 9.3 端口被占用

```bash
ss -ltnp | grep 8000     # 麒麟自带 ss
# 改端口启动
PORT=9000 bash deploy-offline.sh
```

### 9.4 LLM 连接失败

```bash
curl http://内网LLM地址:端口/v1/models    # 测试连通性
grep LLM_ backend/.env                      # 检查配置
# 重新引导配置
rm backend/.env && bash deploy-offline.sh
```
注意 `LLM_BASE_URL` 末尾通常需要 `/v1`。

### 9.5 文件上传失败

```bash
ls -la backend/data/uploads/
chmod 755 backend/data/uploads/
```

### 9.6 前端页面 404

```bash
ls backend/src/static/    # 应有 index.html 与 assets/
```
若缺失，在开发机重新 `npm run build` 并复制 `dist` → `backend/src/static`。

---

## 附录：本离线包已下载内容核对

| 项目 | 内容 |
|------|------|
| 便携 Python | `offline-bundle/python/cpython-3.12.13-x86_64-linux-gnu.tar.gz` |
| Python wheel | `offline-bundle/wheels/*.whl`（cp312 / manylinux x86_64，以实际目录为准） |
| 完整性校验清单 | `offline-bundle/MANIFEST.sha256`（SHA-256 清单，见下方校验命令） |
| 离线依赖清单 | `backend/requirements-offline.txt`（与 `requirements.txt` 内容一致） |
| 一键构建脚本 | `scripts/build-offline-package.sh` |
| 一键部署脚本 | `deploy-offline.sh` |
| 前端产物 | `backend/src/static/`（已内置，无需 Node.js） |

> 校对 wheel 数量：`ls offline-bundle/wheels/*.whl | wc -l`
> 校对便携 Python：`gzip -t offline-bundle/python/cpython-*.tar.gz && echo OK`
> 在目标机上整体校验部署包完整性：`cd offline-bundle && shasum -a 256 -c MANIFEST.sha256`（如无 `shasum`，可用 `sha256sum -c MANIFEST.sha256`）

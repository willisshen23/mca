# Docker + SQLite 一键部署

本方案面向可联网安装 Docker 镜像和依赖的环境。Compose 会启动主应用和银行
营销 Mock 两个容器。前端与后端打入主应用镜像，后端在 `8000` 端口同时提供
页面和 API；宿主机访问端口由 `backend/.env` 的 `PORT` 决定。业务数据和
会话状态全部使用 SQLite，不安装、不启动 MySQL。

## 一、部署前准备

需要安装：

- Docker Desktop（Windows 11/macOS），或 Docker Engine（Linux）
- Docker Compose，以下任意一种命令可用即可：
  - 新版插件：`docker compose version`
  - 旧版独立程序：`docker-compose version`

首次构建镜像需要访问 Node、Python 基础镜像以及 npm、pip 依赖源。

## 二、一键启动

### Windows 11

在项目根目录打开 PowerShell：

```powershell
.\deploy\docker\docker-deploy.ps1
```

### Linux / macOS

在项目根目录执行：

```bash
bash deploy/docker/docker-deploy.sh
```

首次执行会自动：

1. 自动选择 `docker compose` 或 `docker-compose`；
2. 若不存在，则从 `backend/.env.example` 创建 `backend/.env`；
3. 构建前端；
4. 安装后端依赖并构建应用镜像；
5. 构建并启动 Mock 银行营销接口；
6. 创建 SQLite 数据目录；
7. 启动主应用并设置异常自动重启。

访问地址（以 `PORT=9111` 为例）：

```text
http://服务器IP:9111
```

健康检查：

```text
http://服务器IP:9111/health
```

## 三、修改配置

编辑项目统一配置文件 `backend/.env`，至少确认以下配置：

```dotenv
PORT=9111
ALLOWED_ORIGINS=http://服务器IP:9111

LLM_API_KEY=实际密钥
LLM_BASE_URL=http://模型服务地址/v1
LLM_MODEL=实际模型名称

BANK_MARKETING_ACTIVITY_LIST_URL=http://mock:8005/api2/campaigns/search
BANK_MARKETING_TEMPLATE_LIST_URL=http://mock:8005/api2/templates
BANK_MARKETING_COMPONENT_VALUES_URL=http://mock:8005/api2/component-values
BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL=http://mock:8005/api2/dataservice/query/{trade_code}
```

### LLM API Key 密文保存（可选，推荐）

`LLM_API_KEY` 等 `*_LLM_API_KEY` 支持 `enc:v1:` 密文（AES-256-GCM），
明文只在进程内存出现。在 backend 目录下执行：

```bash
python scripts/env_secret.py init                              # 生成主密钥
python scripts/env_secret.py encrypt --env backend/.env        # 明文 → 密文
python scripts/env_secret.py check --env backend/.env --require-encrypted
```

Compose 会把 `backend/.env` 原样注入容器（密文随之进入，没问题），
**主密钥必须与密文物理分离**，两种注入方式：

1. **宿主机环境变量（推荐，最简单）**：compose 已内置 `${LLM_MASTER_KEY:-}`
   透传，部署前在宿主机设置（无需改任何文件）：
   - Windows PowerShell：`$env:LLM_MASTER_KEY = "<hex64>"`
   - Linux/macOS：`export LLM_MASTER_KEY=<hex64>`
2. **密钥文件挂载**：密钥文件放 `deploy/docker/secrets/master.key`（已 gitignore，
   不进入镜像构建上下文），在 `docker-compose.yml` 的 `app` 服务加两行：
   ```yaml
   environment:
     LLM_MASTER_KEY_FILE: /run/secrets/llm-master.key
   volumes:
     - ./secrets/master.key:/run/secrets/llm-master.key:ro
   ```

`docker-deploy.sh` / `docker-deploy.ps1` 会自动预检：检测到密文但宿主机未提供
主密钥时直接报错提示，避免容器启动后才暴露问题。未加密的明文配置完全兼容，
无需改动；主密钥丢失后密文无法恢复，换密钥用 `python scripts/env_secret.py
rotate` 重加密。完整说明见 `docs/LLM-API-KEY-密文配置使用文档.md`。

修改配置后重新创建容器：

```powershell
.\deploy\docker\docker-deploy.ps1 down
.\deploy\docker\docker-deploy.ps1 up
```

Linux/macOS 将脚本名替换为 `bash deploy/docker/docker-deploy.sh`。

注意：容器内的 `127.0.0.1` 指向容器自身，不是宿主机。Windows/macOS 访问
宿主机服务可以使用 `host.docker.internal`；Linux 建议填写宿主机局域网 IP。

默认 Mock 仅通过 Compose 内部网络的 `mock:8005` 提供服务，不占用宿主机
`8005` 端口。主应用会直接调用它。若需要切换真实银行接口，只需把
`backend/.env` 中的四个 `BANK_MARKETING_*_URL` 替换为容器能够访问的真实
地址，然后执行 `down` 和 `up`。

Compose 会把 `backend/.env` 注入主应用容器，不再在 Docker 部署目录维护
第二份环境配置。其中 `PORT` 表示宿主机访问端口，容器内部服务仍固定监听
`8000`。

## 四、常用管理命令

Windows：

```powershell
.\deploy\docker\docker-deploy.ps1 status
.\deploy\docker\docker-deploy.ps1 logs
.\deploy\docker\docker-deploy.ps1 restart
.\deploy\docker\docker-deploy.ps1 down
```

Linux/macOS：

```bash
bash deploy/docker/docker-deploy.sh status
bash deploy/docker/docker-deploy.sh logs
bash deploy/docker/docker-deploy.sh restart
bash deploy/docker/docker-deploy.sh down
```

`down` 只删除容器和网络，不删除 SQLite 数据。

查看两个容器：

```bash
bash deploy/docker/docker-deploy.sh status
```

单独查看 Mock 日志：

```bash
cd deploy/docker
docker-compose -p activity-analysis -f docker-compose.yml logs -f mock
```

## 五、SQLite 数据与备份

所有持久化内容都位于：

```text
deploy/docker/runtime-data/
├── skills.db          业务数据、配置和会话记录
├── v3_checkpoints.db  v3（openJiuwen）会话状态
├── checkpoints.db     v2 历史文件（不再读写，可归档）
├── uploads/           用户上传文件
├── outputs/           报告导出文件
└── logs/              服务日志
```

备份前建议先停止服务，随后整体复制 `deploy/docker/runtime-data`：

```powershell
.\deploy\docker\docker-deploy.ps1 down
Copy-Item -Recurse deploy\docker\runtime-data deploy\docker\runtime-data-backup
```

恢复时停止服务，用备份目录覆盖 `deploy/docker/runtime-data`，再重新启动。

## 六、数据库初始化说明

此部署方式明确把 `DATABASE_HOST` 等 MySQL 配置置空，并固定：

```text
BUSINESS_DATABASE_URL=sqlite:////app/backend/data/skills.db
DB_PATH=/app/backend/data/checkpoints.db
```

其中 `DB_PATH` 为 v2 遗留的会话状态库路径（该文件已不再读写，可归档）。
v3（openJiuwen）会话状态库为 `data/v3_checkpoints.db`，由
`AGENT_V3_CHECKPOINTER_DB_PATH` 控制，默认即在 `/app/backend/data` 挂载卷内。

首次启动时，FastAPI 的启动流程会根据 SQLAlchemy 模型自动创建 SQLite 表，
并执行项目已有的轻量表结构升级。不会执行 `data/mysql/schema.sql`、
`migrate-db.sh` 或 `export_sqlite_to_mysql.py`。

## 七、更新应用

拉取或复制新代码后再次执行一键启动即可：

```powershell
.\deploy\docker\docker-deploy.ps1 up
```

Compose 会重新构建镜像并替换容器，`deploy/docker/runtime-data` 中的数据不会丢失。

# 活动分析助手 Backend

## 项目简介

活动分析助手后端是一个基于 **openJiuwen agent-core** 的智能活动分析服务。系统以
`agent_v3`（ReAct 单智能体 + 工具调用 + 审批护栏）为唯一对话运行时，配合
`report_pipeline` 报告生成流水线，实现"查询活动 → 加入分析队列 → 生成/修改/导出报告"
的全流程对话式分析。

对外提供 FastAPI 网关（统一前缀 `/activity/api`），内置 SPA 静态资源托管、
AuthSDK 鉴权反向代理（`/authApi`），业务数据存储支持 SQLite / MySQL 双后端。

## 技术架构

```
┌──────────────────────────────────────────────────────────────────┐
│                     FastAPI 网关层 (src/main.py)                  │
│  /activity/api/*  业务 API（15 个路由器，统一注册）                │
│  /authApi/*       鉴权服务反向代理（AUTH_SERVICE_BASE_URL）        │
│  /activity/health 健康检查                                        │
│  /*               SPA 静态资源（history 模式兜底 index.html）      │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│              agent_v3 对话运行时（openJiuwen ReActAgent）          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌─────────────┐ │
│  │  Runtime   │  │   Rails    │  │  Sessions  │  │  SSE Bridge │ │
│  │ 请求/取消/ │  │ 审批/限次/ │  │ 会话与状态 │  │ 事件→SSE 帧 │ │
│  │ 缓冲/审计  │  │ 进度/守卫  │  │            │  │             │ │
│  └────────────┘  └────────────┘  └────────────┘  └─────────────┘ │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Tools（12 个）：活动查询/分析队列/模板/技能/报告生成导出等   │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│              report_pipeline 报告生成流水线                       │
│  文件解析 / 模板匹配 / 组件取值 / 外呼数据获取 / 报告合成 /        │
│  HTML 守卫（结构+布局校验）/ 分行下钻                             │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│              Services 业务服务层                                  │
│  技能 / 模板 / 会话 / 运行历史 / 报告导出 / 用量看板 / 系统提示词 │
└──────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│              Infrastructure 基础设施层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐   │
│  │ DB 层        │  │ 银行营销 API │  │ 文件/格式转换/工具     │   │
│  │ SQLite/MySQL │  │ 集成客户端   │  │                       │   │
│  └──────────────┘  └──────────────┘  └───────────────────────┘   │
│  data/skills.db（业务）  data/v3_checkpoints.db（v3 状态持久化）  │
└──────────────────────────────────────────────────────────────────┘
```

## 核心功能

### 1. 对话式智能体（agent_v3）
- 基于 openJiuwen `ReActAgent` 的单智能体运行时（P3 起为唯一运行时，agent_v2 已删除）
- 12 个业务工具：活动查询、活动详情、分析队列增删改、上传数据解析、
  模板/技能查询、报告生成/修改/导出/查看、待办清单
- 自定义 Rail 护栏：写操作审批（三决策）、工具调用上限、工具进度流帧、未知工具守卫
- 会话级取消、断连缓冲重连（SSE）、审批中断恢复（InteractiveInput）、turn 级审计
- v3 状态持久化（`data/v3_checkpoints.db`），服务重启可恢复会话

### 2. 报告生成流水线（report_pipeline）
- 上传文件解析、活动模板匹配、组件数值获取、外呼活动真实数据获取
- 营销报告合成（HTML）、报告结构/布局双重守卫（失败自动重试）
- 分行下钻、组件值清洗、选中活动路由等能力节点

### 3. 技能与模板管理
- SKILL 的增删改查、分类管理、技能迁移、默认分类保护
- 活动分析模板 CRUD 与应用；系统提示词、快捷提示词管理

### 4. 会话与运行历史
- 会话元数据管理、对话日志（turn 级）、Agent 运行历史查询/导出
- 报告版本管理（report_versions）与用户反馈

### 5. 用量看板
- 使用量事件采集、汇总统计、导出

### 6. 外部数据集成
- 银行营销活动 API：活动列表、模板列表、组件数值、外呼活动数据（按交易码）
- 支持 mock/真实接口切换（按配置的 URL 指向）

## 快速开始

### 环境要求

- Python 3.10+
- SQLite 3.0+（默认）或 MySQL 8（生产可选）

### 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 安装依赖（在线）
pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple

# 离线环境
pip install -r requirements-offline.txt --no-index --find-links <离线包目录>
```

### 配置环境变量

复制 `.env.example` 为 `.env` 并配置（`.env.production.example` 为生产模板）：

```env
# 全局 LLM 配置（所有 Agent 的 fallback；支持任意 OpenAI 兼容端点）
LLM_API_KEY=your-api-key
LLM_BASE_URL=http://your-llm-endpoint/v1
LLM_MODEL=qwen3-vl-32b-instruct
LLM_TIMEOUT_SECONDS=600
LLM_MAX_TOKENS=262144
LLM_TEMPERATURE=0.1

# agent_v3 主对话模型（角色名 AGENT_V2_MAIN，需支持 tool calling；缺省回退全局）
# AGENT_V2_MAIN_LLM_API_KEY=
# AGENT_V2_MAIN_LLM_BASE_URL=
# AGENT_V2_MAIN_LLM_MODEL=

# 系统配置
DB_PATH=data/checkpoints.db
BUSINESS_DATABASE_URL=sqlite:///data/skills.db
# DATABASE_HOST 非空时连接 MySQL；留空使用 SQLite
#DATABASE_HOST=
#DATABASE_PORT=
#DATABASE_USERNAME=
#DATABASE_PASSWORD=
#DATABASE_NAME=

UPLOAD_DIR=data/uploads
OUTPUT_DIR=data/outputs
LOG_LEVEL=INFO
LOG_TO_FILE=true

HOST=0.0.0.0
PORT=9111
ALLOWED_ORIGINS=http://localhost:9111

# 活动外部 API（每个接口单独配置完整 URL + 方法）
BANK_MARKETING_API_TOKEN=
BANK_MARKETING_ACTIVITY_LIST_URL=http://localhost:8005/api2/campaigns/search
BANK_MARKETING_TEMPLATE_LIST_URL=http://localhost:8005/api2/templates
BANK_MARKETING_COMPONENT_VALUES_URL=http://localhost:8005/api2/component-values
BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL=http://localhost:8005/api2/dataservice/query/{trade_code}
```

要点：
- 可按角色覆盖 LLM 配置：`{ROLE}_LLM_API_KEY/BASE_URL/MODEL/MAX_TOKENS/TEMPERATURE`，
  角色包括 `SUPERVISOR`、`DATA_ANALYSIS`、`REPORT_GENERATION`、`REPORT_VALIDATION`、
  `FINALIZE`、`AGENT_V2_MAIN`、`AGENT_V2_CHEAP`、`AGENT_V2_FALLBACK`；
- 接口文档默认关闭，联调时设 `ENABLE_DOCS=true` 开启 `/docs`、`/openapi.json`；
- 鉴权代理：`AUTH_SERVICE_BASE_URL` 非空时，`/authApi/*` 转发到鉴权服务。

### LLM API Key 密文保存（可选，推荐生产使用）

`backend/.env` 中的 `*_LLM_API_KEY`（全局 + 各 Agent 角色）支持以密文保存：
明文只在进程内存出现，配置文件/备份/误发文件不含明文。算法为 AES-256-GCM，
密文格式 `enc:v1:<base64(nonce‖ciphertext‖tag)>`，自带完整性校验（篡改即解密失败）。

```bash
# 1. 生成主密钥（写入 backend/data/secrets/master.key，chmod 600）
python scripts/env_secret.py init

# 2. 把 backend/.env 中所有 *_LLM_API_KEY 明文就地替换为密文
python scripts/env_secret.py encrypt --env backend/.env

# 3. 校验（--require-encrypted 严格模式：不允许明文残留）
python scripts/env_secret.py check --env backend/.env --require-encrypted

# 4. 轮换主密钥：旧 key 解密 → 新 key 重加密
python scripts/env_secret.py rotate --env backend/.env --generate-new
```

主密钥注入（二选一，**切勿写进 backend/.env 与密文同文件**）：

| 方式 | 说明 |
|---|---|
| 环境变量 `LLM_MASTER_KEY` | 32 字节主密钥的 hex（64 字符）或 base64（44 字符）；systemd `EnvironmentFile`、docker `environment:` 或宿主机 export 均可 |
| 密钥文件 `LLM_MASTER_KEY_FILE` | 指向密钥文件路径；未设置时默认 `backend/data/secrets/master.key`（已 gitignore） |

- 明文配置完全兼容：不含 `enc:v1:` 前缀的值原样使用，旧部署/测试零改动；
- 密文存在但主密钥缺失 → 进程启动即失败（fail-fast），不会把密文当明文发给上游；
- 同一机制可扩展到 `BANK_MARKETING_API_TOKEN`、`DATABASE_PASSWORD` 等字段；
- 已入库示例文件（`.env.example` / `.env.production.example`）中的历史密钥若曾用于生产，**请视为已泄露并轮换**。

> 完整使用文档（部署、轮换、故障排查、扩展）：[docs/LLM-API-KEY-密文配置使用文档.md](../docs/LLM-API-KEY-密文配置使用文档.md)

### 初始化数据库

```bash
# SQLite：服务首次启动会自动建表；写入种子数据：
python -m src.infrastructure.db.seed
# 或使用脚本
python scripts/init_skill_db.py

# MySQL：先执行 DDL
mysql -u root -p njbank_aa < ../data/mysql/schema.sql
```

### 启动服务

```bash
# 开发模式
python src/main.py

# 或使用 uvicorn
uvicorn src.main:app --host 0.0.0.0 --port 9111 --reload

# 或使用脚本（推荐，含重启/停止）
bash scripts/server.sh start
bash scripts/start.sh
```

### 停止与重启服务

推荐使用 `scripts/server.sh` 统一管理（pid 文件在 `data/run/activity-analysis-assistant.pid`）：

```bash
# 停止（优雅退出，等待进行中的请求收尾）
bash scripts/server.sh stop

# 停止超时后强制杀掉
bash scripts/server.sh stop --force

# 重启（先停后启，等价于 stop + start）
bash scripts/server.sh restart

# 查看运行状态（PID / 地址 / 健康检查）
bash scripts/server.sh status

# 跟踪运行日志
bash scripts/server.sh logs            # tail -f
bash scripts/server.sh logs -n 200 --no-follow
```

其他场景的停止方式：

- **前台运行**（`python src/main.py` / `uvicorn --reload` / `start.sh` 前台模式）：
  直接 `Ctrl + C` 即可。
- **通过 API 重启**：`POST /activity/api/env-config/restart`
  （执行 `BACKEND_RESTART_COMMAND`，默认 `scripts/server.sh restart`），
  前端环境配置页的"重启后端"按钮走的就是这个接口。
- **手动查进程**（pid 文件丢失时）：

  ```bash
  lsof -ti :9111 | xargs kill        # 按端口（以 PORT=9111 为例）
  pkill -f 'uvicorn src.main:app'    # 按进程名
  ```

注意：
- 重启会自动执行数据库迁移（`migrate-db.sh auto`），依赖未变化时秒级完成；
- 会话状态已持久化到 `data/v3_checkpoints.db`，重启后可恢复；
- 修改 `.env` 配置后必须重启才能生效。

### 主对话上下文管理

agent_v3 使用 openJiuwen 原生 ContextEngine，默认按以下顺序处理历史：

1. `MessageOffloader` 将超过阈值的历史大 tool 消息替换为短前缀和 reload marker，原文写入专用 workspace；
2. `DialogueCompressor` 超阈值时调用主模型，将历史工具型 ReAct 块替换为摘要，保留最近消息和最后一轮；
3. 发送给模型时只取最近 20 个完整对话轮，checkpoint 不设置消息数硬上限。

reload 默认启用：模型需要原文时，可根据 marker 中的精确 `path` 调用原生 `read_file` 恢复。`AGENT_V3_CONTEXT_WORKSPACE_DIR` 默认为 `data/agent_workspace`，文件工具通过沙箱限制只能读取该目录；`AGENT_V3_CONTEXT_RELOAD_ENABLED=false` 可关闭恢复链路。

通过 `AGENT_V3_CONTEXT_*` 环境变量调整阈值或关闭对应能力，详见 `.env.example`。压缩模型复用主模型配置；压缩调用失败时框架保留原消息并继续执行。

### 访问服务

- 健康检查: http://localhost:9111/activity/health
- API 文档（需 `ENABLE_DOCS=true`）: http://localhost:9111/docs
- 前端页面（已构建静态资源时）: http://localhost:9111/

## API 接口

所有业务接口挂载在 `/activity/api` 前缀下。

### 对话智能体（agent_v3 运行时，`/v2/agent`）

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/v2/agent/run` | 发起一轮对话/任务 |
| GET | `/v2/agent/runs/{thread_id}` | 查询运行状态 |
| GET | `/v2/agent/runs/{thread_id}/stream` | SSE 事件流（断连可重连续传） |
| POST | `/v2/agent/cancel` | 取消运行 |
| POST | `/v2/agent/resume` | 审批后恢复运行 |
| GET | `/v2/agent/components` | 可用组件 |
| GET | `/v2/agent` / `/v2/agent/thread/{thread_id}` | 会话信息查询 |

### 技能管理

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/skills` | 获取技能列表 |
| POST | `/skills` | 新增技能 |
| PATCH | `/skills/{skill_id}` | 更新技能 |
| DELETE | `/skills/{skill_id}` | 删除技能 |
| PATCH | `/skills/{skill_id}/category` | 技能迁移分类 |
| GET | `/skill-categories` | 获取分类列表 |
| POST | `/skill-categories` | 新增分类 |
| DELETE | `/skill-categories/{category_id}` | 删除分类 |

### 文件处理

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/upload` | 上传文件（CSV/Excel） |
| GET | `/download/{file_name}` | 下载文件 |
| GET | `/report-exports/{file_name}` | 下载导出的报告 |

### 报告

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/reports/html` | 生成/获取 HTML 报告 |

### 活动分析模板（`/activity-templates`）

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/activity-templates` | 模板列表 |
| POST | `/activity-templates` | 新增模板 |
| PATCH | `/activity-templates/{template_id}` | 更新模板 |
| DELETE | `/activity-templates/{template_id}` | 删除模板 |
| POST | `/activity-templates/{template_id}/apply` | 应用模板 |

### 会话与日志

| 方法 | 路径 | 描述 |
|------|------|------|
| GET/POST | `/conversations` | 会话列表 / 新建会话 |
| GET/PATCH/DELETE | `/conversations/{thread_id}` | 会话详情 / 更新 / 删除 |
| GET | `/conversation-logs` | 对话日志查询 |
| GET | `/agent-run-history` 等 | 运行历史查询、会话导出、报告版本、用户反馈 |
| GET | `/logs/files` `/logs/content` `/logs/tail` `/logs/download/{filename}` | 服务日志查看 |

### 配置与看板

| 方法 | 路径 | 描述 |
|------|------|------|
| GET/PATCH | `/env-config` | 环境配置查看/修改 |
| POST | `/env-config/restart` | 重启后端（执行 `BACKEND_RESTART_COMMAND`，默认 `scripts/server.sh restart`） |
| GET/POST/PATCH/DELETE | `/quick-prompts` 系列 | 快捷提示词管理（含 admin 批量配置） |
| GET/POST/PATCH | `/system-prompts` 系列 | 系统提示词管理（含 publish 发布） |
| GET | `/online-activities` | 线上活动配置查询 |
| GET | `/components` | 分析组件列表 |
| POST | `/usage-dashboard/events` | 用量事件上报 |
| GET | `/usage-dashboard/summary` `/usage-dashboard/export` | 用量汇总 / 导出 |

> 完整接口清单见 [docs/API接口清单.md](../docs/API接口清单.md)。

## 项目结构

```
backend/
├── src/
│   ├── main.py                        # 应用入口：FastAPI、中间件、生命周期、日志、SPA 托管
│   ├── config.py                      # 配置管理（Pydantic Settings，含密文解密）
│   ├── secrets.py                     # 主密钥加载与 AES-256-GCM 解密
│   ├── llm.py                         # LLM 工厂（LoggingModel、温度解析）
│   ├── agent_v3/                      # openJiuwen 对话运行时（唯一允许 import openjiuwen 的包）
│   │   ├── agent_factory.py           # ReActAgent 进程级单例组装（模型配置、Rails、工具挂载）
│   │   ├── runtime.py                 # 请求驱动运行：缓冲注册表、取消、turn 审计、审批恢复
│   │   ├── rails.py                   # 自定义 Rail：审批三决策/工具限次/进度帧/未知工具守卫
│   │   ├── sessions.py                # 会话管理
│   │   ├── request_context.py         # 请求级上下文（thread_id/user 等）
│   │   ├── events/                    # SSE 事件桥
│   │   │   ├── _frames.py             # 帧构造（摘要/截断/剥字段，与 Rail 复用）
│   │   │   └── sse_bridge.py          # openJiuwen 事件 → SSE 帧
│   │   ├── prompts/                   # 系统提示词与分析视角
│   │   │   ├── system.py              # 系统提示词构建
│   │   │   └── perspectives.py        # 分析视角（外呼/短信/综合运营）
│   │   ├── state/
│   │   │   └── persistence.py         # v3 checkpointer（data/v3_checkpoints.db）
│   │   └── tools/                     # 12 个业务工具（ToolContext 适配层）
│   │       └── impl/                  # 工具实现
│   │           ├── activity_query.py      # 活动查询/详情
│   │           ├── analysis_queue.py      # 分析队列增删改
│   │           ├── data_parse.py          # 上传文件解析
│   │           ├── template.py            # 模板查询
│   │           ├── skill.py               # 技能查询
│   │           ├── report_gen.py          # 报告生成（调 report_pipeline）
│   │           ├── report_modify.py       # 报告修改
│   │           ├── report_export.py       # 报告导出
│   │           ├── context.py             # 报告上下文查看
│   │           └── common.py              # 公共工具逻辑
│   ├── report_pipeline/               # 报告生成流水线
│   │   ├── state.py                   # 流水线共享状态（AgentState 契约）
│   │   ├── defaults.py                # 默认配置
│   │   ├── period.py                  # 分析周期处理
│   │   ├── prompts/marketing_workflow.py  # 营销报告提示词
│   │   └── capabilities/              # 能力节点（13 个）
│   │       ├── activity_file_parse.py         # 活动文件解析
│   │       ├── activity_template_matching.py  # 活动模板匹配
│   │       ├── template_list_fetch.py         # 模板列表获取
│   │       ├── template_matching.py           # 模板匹配
│   │       ├── component_value_fetch.py       # 组件数值获取
│   │       ├── component_value_cleanup.py     # 组件值清洗
│   │       ├── uploaded_component_value_extract.py # 上传数据组件值提取
│   │       ├── outbound_activity_data_fetch.py # 外呼活动真实数据获取
│   │       ├── selected_activity_router.py    # 选中活动路由
│   │       ├── branch_drilldown.py            # 分行下钻
│   │       ├── marketing_report_synthesis.py  # 营销报告合成（HTML）
│   │       ├── report_html_guard.py           # 报告 HTML 结构守卫
│   │       └── report_layout_guard.py         # 报告布局守卫
│   ├── api/                           # API 接口层
│   │   ├── routes.py                  # 主路由（create_api_router）
│   │   ├── schemas.py                 # 请求/响应模型
│   │   ├── auth_proxy.py              # /authApi 鉴权反向代理
│   │   └── routers/                   # 15 个路由器
│   │       ├── agent_v2.py                # 对话智能体（/v2/agent，v3 运行时入口）
│   │       ├── skills.py                  # 技能/分类
│   │       ├── files.py                   # 文件上传/下载
│   │       ├── reports.py                 # 报告
│   │       ├── components.py              # 分析组件
│   │       ├── activity_templates.py      # 活动分析模板
│   │       ├── system_prompts.py          # 系统提示词
│   │       ├── quick_prompts.py           # 快捷提示词
│   │       ├── env_config.py              # 环境配置/重启
│   │       ├── conversations.py           # 会话
│   │       ├── conversation_logs.py       # 对话日志
│   │       ├── agent_run_history.py       # 运行历史/报告版本/反馈
│   │       ├── logs.py                    # 服务日志查看
│   │       ├── online_activities.py       # 线上活动
│   │       └── usage_dashboard.py         # 用量看板
│   ├── services/                      # 业务服务层
│   │   ├── skill_service.py               # 技能业务（含 usage schema 保障）
│   │   ├── activity_template_service.py   # 活动模板
│   │   ├── agent_run_history_service.py   # 运行历史/报告版本
│   │   ├── conversation_log_service.py    # 对话 turn 审计
│   │   ├── env_config_service.py          # 环境配置
│   │   ├── marketing_api_service.py       # 营销 API 编排
│   │   ├── quick_prompt_service.py        # 快捷提示词
│   │   ├── report_export_service.py       # 报告导出（HTML/DOCX/PDF）
│   │   ├── system_prompt_service.py       # 系统提示词
│   │   ├── uploaded_file_service.py       # 上传文件管理
│   │   └── usage_export_service.py        # 用量导出
│   ├── domain/                        # 领域层
│   │   ├── activity_status.py             # 活动状态
│   │   ├── components/                    # 分析组件（base/overview/registry）
│   │   └── report/                        # 报告模板（html_template/template_skill）
│   ├── infrastructure/                # 基础设施层
│   │   ├── db/                          # SQLAlchemy 模型/会话/迁移/种子
│   │   ├── integrations/bank_marketing/   # 银行营销 API 客户端与数据模型
│   │   ├── files/file_reader.py           # CSV/Excel 解析
│   │   ├── converters/format_converter.py # 格式转换
│   │   ├── tools/function_call.py         # 函数调用工具
│   │   └── static/                        # 前端构建产物（SPA 托管）
│   └── utils/token_budget.py          # token 预算估算（tiktoken，离线退化字符估算）
├── data/                              # 运行数据（gitignore）
│   ├── skills.db                      # 业务数据库（SQLite 模式）
│   ├── v3_checkpoints.db              # agent_v3 状态持久化
│   ├── uploads/                       # 上传文件
│   ├── logs/                          # 按天轮转日志（app-YYYY-MM-DD.log）
│   └── secrets/                       # 主密钥（master.key，chmod 600）
├── scripts/
│   ├── env_secret.py                  # LLM API Key 密文工具（init/encrypt/check/rotate）
│   ├── server.sh                      # 服务启停/重启（后端重启按钮默认调用）
│   ├── start.sh / start-offline.sh    # 启动脚本（在线/离线）
│   ├── build.sh                       # 构建脚本
│   ├── init_skill_db.py               # 技能库初始化
│   ├── migrate_db.py / migrate-db.sh  # 数据库迁移
│   └── export_sqlite_to_mysql.py      # SQLite → MySQL 数据导出
├── tests/                             # pytest 测试（含 agent_v3/ 与 infrastructure/ 子目录）
├── .env.example                       # 环境变量示例（开发）
├── .env.production.example            # 环境变量示例（生产）
├── pyproject.toml                     # 项目配置与依赖
├── requirements.txt                   # 依赖列表
└── requirements-offline.txt           # 离线依赖列表
```

## agent_v3 运行时说明

### 工具清单（12 个）

| 工具 | 说明 | 类型 |
|------|------|------|
| `search_activities` | 按关键词/渠道/日期查询银行营销活动 | 读 |
| `get_activity_detail` | 查看单个活动详情（先查缓存，未命中回源） | 读 |
| `add_to_analysis_queue` | 将已核实活动加入待分析队列 | 写（需审批） |
| `remove_from_analysis_queue` | 将活动移出分析队列 | 写（需审批） |
| `update_analysis_config` | 调整队列中活动的指标/维度/视角 | 写（需审批） |
| `parse_uploaded_data` | 解析用户上传的活动数据文件 | 读 |
| `get_available_templates` | 查询可用分析报告模板 | 读 |
| `get_available_skills` | 查询全部分析技能（组件） | 读 |
| `generate_report` | 为指定活动生成 HTML 分析报告 | 写 |
| `modify_report` | 按结构化指令修改当前报告（产生新版本） | 写（需审批） |
| `export_report` | 导出当前报告为 HTML 文件 | 写 |
| `get_report_content` | 查看当前报告摘要与版本信息 | 读 |

### Rail 护栏

| Rail | 职责 |
|------|------|
| `ApprovalEditRail` | 写工具调用前中断等待用户审批（通过/修改/拒绝三决策），审批经 `InteractiveInput` 恢复，支持二次审批 |
| `ToolCallLimitRail` | 单轮工具调用次数上限，防失控循环 |
| `ToolProgressRail` | 工具进度转 SSE 帧，前端实时可见 |
| `UnknownToolGuardRail` | 模型幻觉出未注册工具时的守卫 |

### 关键机制

- **单实例单活跃 run**：同一 `thread_id` 同时仅一个活跃 run（取消注册表约束）；
- **断连重连**：run 独立于浏览器连接存活（`_BufferedRun`），SSE 重连后从缓冲续传；
- **取消**：在流事件间隙生效，前端取消按钮即达；
- **审计**：每 turn 经 `conversation_log_service` 记录开始/结束；
- **持久化**：`v3_checkpoints.db`（SQLite WAL），服务重启会话可恢复；
- **导入隔离**：全仓库仅 `src/agent_v3/` 包内允许 `import openjiuwen`。

## 数据库

业务库默认 SQLite（`data/skills.db`），`DATABASE_HOST` 非空时切换 MySQL。
启动时自动：建缺失表 → 执行列级迁移（`migrations.py`）→ 清理 v1 遗留数据。

主要表：`skill_categories`、`skills`、`skill_versions`、`skill_tags`、
`analysis_frameworks`、`activity_analysis_templates`、`SYSTEM_PROMPT`、
`quick_prompts`、`usage_events`、`llm_token_usage_logs`、`skill_usage_logs`、
`conversation_meta`、`conversation_turn`、`agent_run_history`、`report_versions`。

## 技术栈

| 分类 | 技术 | 版本 |
|------|------|------|
| 框架 | FastAPI | 0.130+ |
| 智能体 | openJiuwen agent-core（ReActAgent + Rail + Runner） | - |
| LLM 接入 | OpenAI 兼容端点（langchain-openai 等） | - |
| 任务编排 | LangGraph / deepagents（流水线与工具底层） | 1.2+ / 0.6.12 |
| 数据库 | SQLAlchemy 2（SQLite / MySQL） | 2.0+ |
| 数据分析 | Pandas / OpenPyXL | 2.0+ |
| 报告生成 | WeasyPrint / python-docx / BeautifulSoup4 | 62+ |
| 实时通信 | sse-starlette | 2.0+ |
| token 估算 | tiktoken（离线退化字符估算） | 0.7+ |

## 开发指南

### 添加新的业务工具

1. 在 `src/agent_v3/tools/impl/` 下实现工具逻辑（同步函数，接 `ToolContext`）
2. 在 `src/agent_v3/tools/__init__.py` 注册 schema、`TOOL_DISPLAY_NAMES`，
   写操作加入 `WRITE_TOOLS`（自动走审批 Rail）
3. 如需进度反馈，经 `ToolContext.write_stream` 发送进度事件

### 添加新的流水线能力节点

1. 在 `src/report_pipeline/capabilities/` 下创建能力文件
2. 状态契约更新 `src/report_pipeline/state.py`
3. 在报告生成入口（`tools/impl/report_gen.py`）中编排调用

### 添加新的 API 路由

1. 在 `src/api/routers/` 下创建路由文件
2. 在 `src/api/routers/__init__.py` 的 `create_api_router()` 中注册

### 运行测试

```bash
pytest tests/                 # 全量
pytest tests/agent_v3/        # 仅 v3 运行时
```

## 部署说明

### 生产环境部署

```bash
pip install -e . --no-dev
# 配置 .env（参考 .env.production.example），MySQL 见上文初始化
bash scripts/server.sh start    # 或 systemd / supervisor 托管
```

前端构建产物放入 `src/infrastructure/static/` 后由后端直接托管
（Vue history 模式已做 404 兜底）。生产部署在 `/data-ai/marketing/activity/` 子路径，
前端资源路径在运行时解析。

> Docker 镜像部署详见 [docs/营销活动分析助手-Docker镜像部署文档(Linux).docx](../docs/营销活动分析助手-Docker镜像部署文档(Linux).docx)。

## 安全注意事项

1. 接口文档默认关闭（`ENABLE_DOCS` 仅在联调时开启）
2. 配置适当的 CORS 策略（`ALLOWED_ORIGINS` 白名单）
3. 对上传文件进行类型和大小限制
4. LLM API Key 使用密文保存（见上文密文配置章节），主密钥与密文物理分离
5. 对用户输入进行严格验证；写操作经审批 Rail 二次确认
6. 定期备份数据库与 `data/` 目录

## 许可证

MIT License

## 联系方式

如有问题或建议，请联系开发团队。

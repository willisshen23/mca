# 活动分析助手

面向银行营销场景的对话式活动分析助手。用户通过自然语言查询营销活动、组装分析队列，由 **deepagents 自主智能体（agent_v2）** 调用业务工具完成数据拉取、报告生成、报告修改与 HTML 导出，写操作经 HITL 人工审批后执行。

> 旧版 LangGraph Supervisor 多智能体链路（v1）已废弃下线，agent_v2 是当前唯一的智能体运行时。设计与交接文档见 `docs/superpowers/specs/`。

## 架构概述

```
┌─────────────────────────────────────────────────────────┐
│                 Vue 3 Frontend (:3000 dev)               │
│  对话界面 · 审批卡片 · 报告预览 · 技能/模板/历史/日志管理  │
│  生产模式下构建产物由后端静态托管（同 :8000）              │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / SSE
                           ▼
┌─────────────────────────────────────────────────────────┐
│                FastAPI Backend (:8000)                   │
│  /api/v2/agent/* · /api/conversations · /api/skills · … │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│            agent_v2（deepagents 自主智能体）              │
│                                                          │
│  多模型路由：主推理模型 / 轻量模型 / 降级备选模型           │
│     │                                                    │
│  12 个业务工具 + write_todos（白名单，已剥离 execute/fs） │
│     │  写工具经 interrupt_on 硬中断 → 前端审批卡片 → resume│
│     ▼                                                    │
│  report_pipeline 报告生成管线（模板匹配/数值拉取/HTML 守卫）│
│                                                          │
│  LangGraph Checkpoint 持久化多轮会话（SQLite / MySQL）     │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP
                           ▼
┌─────────────────────────────────────────────────────────┐
│        银行营销外部 API（开发态由 mock/ 服务 :8005 模拟）   │
│  活动搜索 · 模板清单 · 组件数值 · 外呼活动数据              │
└─────────────────────────────────────────────────────────┘
```

## 技术栈

| 层 | 技术 |
|----|------|
| 智能体框架 | deepagents 0.6.12（基于 LangGraph 1.x / LangChain 1.x） |
| HITL | deepagents 原生 `interrupt_on` 硬中断 + `/resume` 恢复 |
| LLM | 任意兼容 OpenAI API 的服务（langchain-openai），按角色多模型路由 |
| 后端 | FastAPI + Uvicorn + sse-starlette 流式推送 |
| 数据库 | MySQL（生产，`DATABASE_*` 配置）或 SQLite（本地兜底），SQLAlchemy + 启动期自动迁移 |
| 前端 | Vue 3 + Vite + vue-router（构建产物由后端静态托管） |
| 文件解析 | pandas + openpyxl（CSV/Excel 上传数据） |
| HTML→DOCX | python-docx + beautifulsoup4 |

## 项目结构

```
njbank_Marketing_Campaign_Analysis/
├── README.md
├── DEPLOY.md                          # 部署指南（含离线部署）
├── DEPLOY-OFFLINE-KYLIN.md            # 麒麟系统离线部署手册
├── docs/                              # 需求说明书、设计文档、superpowers specs/plans
├── mock/                              # 银行营销外部 API 的 mock 服务 (:8005)
│
├── backend/                           # Python 后端
│   ├── pyproject.toml                 # 依赖声明
│   ├── requirements.txt / requirements-offline.txt
│   ├── .env.example                   # 环境变量模板
│   ├── data/                          # uploads / outputs / logs / sqlite 兜底库
│   ├── scripts/                       # init_skill_db、export_sqlite_to_mysql 等
│   ├── tests/                         # pytest（含 tests/agent_v2/）
│   └── src/
│       ├── main.py                    # FastAPI 入口：启动迁移、日志轮转、静态托管
│       ├── config.py                  # Settings + 按角色 LLM 实例（多模型路由配置）
│       ├── ARCHITECTURE.md            # 后端分层约束说明
│       ├── api/
│       │   ├── routes.py              # 路由聚合
│       │   └── routers/               # agent_v2 / conversations / files / reports /
│       │                              # skills / activity_templates / system_prompts /
│       │                              # quick_prompts / env_config / conversation_logs /
│       │                              # agent_run_history / logs / components
│       ├── agent_v2/                  # deepagents 智能体（唯一运行时）
│       │   ├── agent_factory.py       # Agent 构建、写工具 interrupt_on 配置
│       │   ├── runtime.py             # run / cancel / resume 驱动 + turn 级审计
│       │   ├── events/sse_bridge.py   # LangGraph 流 → SSE 帧
│       │   ├── routing/model_router.py# 主/轻量/备选模型分层路由
│       │   ├── prompts/               # system prompt + 视角注入
│       │   ├── state/                 # AgentV2Context / checkpoint 持久化 / 请求上下文
│       │   └── tools/                 # 12 个业务工具（见下）
│       ├── report_pipeline/           # 报告生成管线（被 generate_report 复用）
│       │   └── capabilities/          # 模板匹配、组件数值拉取、外呼数据、HTML/版式守卫…
│       ├── services/                  # 应用协调层（会话日志、技能、模板、导出…）
│       ├── domain/                    # 纯业务规则（组件注册表、报告模板）
│       └── infrastructure/            # db(models/migrations/seed/session)、银行营销
│                                      # API client、文件读取、格式转换、前端静态产物
│
└── frontend/                          # Vue 3 前端
    ├── package.json / vite.config.js  # dev :3000，/api 代理到 :8000
    └── src/
        ├── views/                     # UiChatView(主对话) / SkillComposer / Report /
        │                              # Template / History / ConversationLogs /
        │                              # SkillManagement / Settings / Logs …
        ├── components/                # ChatPanel、审批卡片、报告图表、技能画布…
        ├── api/                       # agentRun(SSE) / conversations / skills …
        ├── router/ stores/ composables/ utils/
```

## 快速开始

### 前置条件

- Python 3.10+
- Node.js 18+
- 兼容 OpenAI API 的 LLM 服务（**端点必须支持 tool calling / function calling**）

### 1. 配置环境变量

```bash
cd backend
cp .env.example .env
```

编辑 `.env`，最小配置（全局 LLM 三件套，所有角色的 fallback）：

```env
LLM_API_KEY=your-key
LLM_BASE_URL=http://your-llm-endpoint/v1
LLM_MODEL=your-model
```

支持内网 GPUStack / vLLM / Ollama / DashScope / OpenAI / DeepSeek 等，详见 `DEPLOY.md`。agent_v2 可按角色单独覆盖模型（不配置则回落全局）：

```env
AGENT_V2_MAIN_LLM_MODEL=...      # 主推理模型（首轮/复杂请求）
AGENT_V2_CHEAP_LLM_MODEL=...     # 轻量模型（短确认/闲聊，可选）
AGENT_V2_FALLBACK_LLM_MODEL=...  # 降级备选（主模型异常时兜底，需与主模型不同才有意义）
```

外部营销 API 默认指向本地 mock（`http://localhost:8005/api2/...`），生产环境改为真实接口地址。

### 2. 安装依赖

```bash
# 后端
cd backend
pip install -e .

# 前端
cd ../frontend
npm install
```

### 3. 启动服务

```bash
# 终端 1 — 后端 (http://localhost:8000)
cd backend
python -m src.main

# 终端 2 — 前端 (http://localhost:3000，/api 已代理到 8000)
cd frontend
npm run dev

# 终端 3 — mock 外部营销 API (http://localhost:8005，可选但推荐)
cd mock
uvicorn app:app --reload --port 8005
```

生产模式：`cd frontend && npm run build`，将构建产物放入 `backend/src/infrastructure/static/`，后端同端口托管前端（详见 `DEPLOY.md`）。

## agent_v2 智能体

### 业务工具（12 个）

| 工具 | 说明 | 类型 |
|------|------|------|
| `search_activities` | 按关键词/类型/时间搜索营销活动 | 只读 |
| `get_activity_detail` | 查看活动详情 | 只读 |
| `get_available_templates` | 获取可用分析模板 | 只读 |
| `get_available_skills` | 获取可用分析组件（技能） | 只读 |
| `parse_uploaded_data` | 解析用户上传的 CSV/Excel | 只读 |
| `get_report_content` | 查看当前报告内容 | 只读 |
| `generate_report` | 生成 HTML 分析报告（走 report_pipeline） | 生成 |
| `export_report` | 导出报告为 HTML | 生成 |
| `add_to_analysis_queue` | 将活动加入分析队列 | **写（需审批）** |
| `remove_from_analysis_queue` | 将活动移出分析队列 | **写（需审批）** |
| `update_analysis_config` | 调整分析配置（模板/时间范围等） | **写（需审批）** |
| `modify_report` | 增量修改报告（产生新版本） | **写（需审批）** |

### HITL 审批流

写工具在 `agent_factory` 中配置 `interrupt_on` 硬中断：LLM 发起写调用 → 图在 `__interrupt__` 暂停 → 后端推送 `approval_required` SSE 帧 → 前端展示审批卡片 → 用户选择 approve / edit（可改参数）/ reject → `POST /api/v2/agent/resume` 携带决策恢复执行。刷新页面后审批状态可从 checkpoint 恢复。

### 多模型路由

两层路由：`TieredModelMiddleware` 按轮次选择主/轻量模型；工具内部经 `get_llm()` 按角色取模型；主模型调用异常时回落备选模型。

### 会话持久化与审计

- LangGraph checkpoint 按 `thread_id` 持久化多轮状态（同一 thread 同时仅一个活跃 run，支持取消）。
- turn 级审计写入 `conversation_log`；报告级运行历史写入 `agent_run_history`，报告每次修改产生版本链（`report_versions`）。

### SSE 事件

`POST /api/v2/agent/run` 流式返回：

```
data: {"type":"node_update","payload":{...}}        # 工具/管线进度
data: {"type":"approval_required","payload":{...}}  # 写操作待审批
data: {"type":"report","payload":{...}}             # 报告生成/新版本
data: {"type":"done","payload":{...}}
data: {"type":"cancelled","payload":{...}}
```

## API 文档

启动后端后访问 `http://localhost:8000/docs` 查看 Swagger UI。

### 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v2/agent/run` | SSE 流式对话（一轮 agent 运行） |
| `POST` | `/api/v2/agent/resume` | 审批决策后恢复执行（SSE） |
| `POST` | `/api/v2/agent/cancel` | 取消正在运行的任务 |
| `GET/POST/PATCH/DELETE` | `/api/conversations[/{thread_id}]` | 会话管理 |
| `POST` | `/api/upload` | 上传 CSV/Excel |
| `GET` | `/api/download/{file_name}` | 下载生成的文件 |
| `POST` | `/api/reports/html` | 下载独立 HTML 报告 |
| `GET/POST/PATCH/DELETE` | `/api/skills`、`/api/skill-categories` | 分析技能（组件）管理 |
| `GET` | `/api/components` | 分析组件注册表 |
| `GET/…` | `/api/activity-templates` | 活动分析模板管理 |
| `GET/…` | `/api/system-prompts` | System Prompt 管理 |
| `GET/…` | `/api/quick-prompts` | 快捷提问管理 |
| `GET` | `/api/conversation-logs` | 对话审计日志 |
| `GET` | `/api/agent-run-history` | 报告运行历史与版本 |
| `GET/PATCH` | `/api/env-config`（`POST /restart`） | 运行时配置查看/修改/重启 |
| `GET` | `/api/logs/files`、`/content`、`/tail`、`/download/{filename}` | 服务日志查看 |
| `GET` | `/health` | 健康检查 |

## 测试

```bash
cd backend
python -m pytest tests/          # 全量（含 tests/agent_v2/ 智能体工具与 HITL 用例）
```

## 相关文档

| 文档 | 说明 |
|------|------|
| `DEPLOY.md` | 部署指南（LLM 配置、打包、运维） |
| `DEPLOY-OFFLINE-KYLIN.md` | 麒麟（Kylin）系统离线部署手册 |
| `backend/src/ARCHITECTURE.md` | 后端分层约束（api/services/domain/infrastructure） |
| `docs/需求说明书.md` | 业务需求 |
| `docs/superpowers/specs/agent-v2-progress.md` | agent_v2 里程碑进度与关键决策（M1–M3 已交付） |
| `docs/superpowers/specs/2026-07-16-deepagent-architecture-design.md` | agent_v2 架构设计 |
| `mock/README.md` | mock 服务接口说明 |

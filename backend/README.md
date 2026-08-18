# 活动分析助手 Backend

## 项目简介

活动分析助手是一个基于 **LangGraph** 多智能体协作系统的活动分析平台。该系统采用监督式多智能体模式，由 Supervisor 协调各子智能体节点，实现自动化的活动数据分析和报告生成。

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI 网关层                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐       │
│  │/api/v1  │  │/api/v1  │  │/api/v1  │  │/api/v1  │       │
│  │/skills  │  │/files   │  │/analysis│  │/chat    │       │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘       │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph 多智能体层                      │
│  ┌───────────────┐    ┌───────────────┐                    │
│  │  Supervisor   │◄───│  Coordinator  │                    │
│  │   (监督者)    │    │    (协调器)   │                    │
│  └───────┬───────┘    └───────┬───────┘                    │
│          │                    │                            │
│  ┌───────┴───────┬────────────┴─────────────┐              │
│  │   Agents      │       Services           │              │
│  │ Intent/Report │   GraphRun/SkillService  │              │
│  └───────────────┴──────────────────────────┘              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    数据持久化层                              │
│  ┌────────────────┐  ┌────────────────┐                    │
│  │  skills.db     │  │ checkpoints.db │                    │
│  │ (业务数据)     │  │ (状态持久化)   │                    │
│  └────────────────┘  └────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

## 核心功能

### 1. 技能管理 (Skill Management)
- SKILL 的增删改查
- 分类管理与技能迁移
- 默认分类保护机制

### 2. 文件处理 (File Processing)
- CSV/Excel 文件上传
- 数据解析与验证
- 支持多种数据源格式

### 3. 分析引擎 (Analysis Engine)
- 活动参与率分析
- 客群行为标签分析
- 渠道效果对比
- 活动ROI分析
- 转化路径分析

### 4. 报告生成 (Report Generation)
- 自动化报告生成
- 支持 HTML 报告输出与 DOCX 格式转换
- 自定义报告模板

### 5. 意图识别 (Intent Recognition)
- 用户意图理解与分类
- 任务分解与规划
- 智能路由分发

## 快速开始

### 环境要求

- Python 3.10+
- SQLite 3.0+

### 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 安装依赖
pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 配置环境变量

复制 `.env.example` 为 `.env` 并配置：

```env
# 服务配置
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080

# 数据库配置
DATABASE_URL=sqlite:///./data/skills.db
CHECKPOINT_DB_URL=sqlite:///./data/checkpoints.db

# OpenAI 配置
OPENAI_API_KEY=your-api-key-here
OPENAI_MODEL=gpt-4o-mini
```

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
python -m src.db.seed
```

### 启动服务

```bash
# 开发模式
python src/main.py

# 或使用 uvicorn
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

### 访问服务

- API 文档: http://localhost:8000/docs
- 健康检查: http://localhost:8000/health

## API 接口

### 技能管理

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/v1/skills` | 获取技能列表 |
| POST | `/api/v1/skills` | 新增技能 |
| GET | `/api/v1/skills/{id}` | 获取技能详情 |
| PUT | `/api/v1/skills/{id}` | 更新技能 |
| DELETE | `/api/v1/skills/{id}` | 删除技能 |
| GET | `/api/v1/skill-categories` | 获取分类列表 |
| POST | `/api/v1/skill-categories` | 新增分类 |
| DELETE | `/api/v1/skill-categories/{id}` | 删除分类 |

### 文件处理

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/files/upload` | 上传文件 |
| GET | `/api/v1/files/{id}` | 获取文件信息 |
| DELETE | `/api/v1/files/{id}` | 删除文件 |

### 分析任务

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/analysis/run` | 执行分析任务 |
| GET | `/api/v1/analysis/{id}` | 获取分析结果 |
| POST | `/api/v1/analysis/export` | 导出分析报告 |

### 实时对话

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/chat` | 实时对话接口（SSE） |

## 项目结构

```
backend/
├── src/                              # 源代码目录
│   ├── agents/                       # 智能体节点（12个）
│   │   ├── __init__.py               # 模块初始化
│   │   ├── component_value_fetch.py  # 组件值获取
│   │   ├── data_analysis.py          # 数据分析
│   │   ├── file_upload.py            # 文件上传
│   │   ├── finalize.py               # 结果汇总
│   │   ├── format_conversion.py      # 格式转换
│   │   ├── intent_recognition.py     # 意图识别
│   │   ├── marketing_data_fetch.py   # 活动数据获取
│   │   ├── marketing_report_synthesis.py # 报告合成
│   │   ├── report_generation.py      # 报告生成
│   │   ├── report_validation.py      # 报告验证
│   │   ├── template_matching.py      # 模板匹配
│   │   └── utils.py                  # 智能体工具函数
│   ├── api/                          # API 接口层
│   │   ├── routers/                  # 路由定义
│   │   │   ├── __init__.py
│   │   │   ├── skills.py             # 技能管理路由
│   │   │   ├── files.py              # 文件处理路由
│   │   │   ├── analysis.py           # 分析任务路由
│   │   │   └── components.py         # 组件管理路由
│   │   ├── __init__.py
│   │   ├── schemas.py                # 数据模型定义
│   │   └── routes.py                 # 路由注册
│   ├── components/                   # 分析组件
│   │   ├── __init__.py
│   │   ├── base.py                   # 组件基类
│   │   ├── overview.py               # 概览组件
│   │   └── registry.py               # 组件注册
│   ├── db/                           # 数据库层
│   │   ├── __init__.py
│   │   ├── models.py                 # SQLAlchemy 模型
│   │   ├── session.py                # 数据库会话
│   │   └── seed.py                   # 初始化数据
│   ├── graph/                        # LangGraph 智能体（7个）
│   │   ├── __init__.py               # 模块初始化
│   │   ├── builder.py                # 图构建器
│   │   ├── checkpoint.py             # 状态持久化
│   │   ├── node_registry.py          # 节点注册
│   │   ├── planning.py               # 任务规划
│   │   ├── state.py                  # 状态定义
│   │   └── supervisor.py             # 监督者节点
│   ├── integrations/                 # 外部集成
│   │   ├── bank_marketing/           # 活动数据集成
│   │   │   ├── __init__.py
│   │   │   ├── client.py             # API 客户端
│   │   │   ├── mock_data.py          # 模拟数据
│   │   │   └── schemas.py            # 数据模型
│   │   └── __init__.py
│   ├── prompts/                      # 提示词模板
│   │   ├── __init__.py
│   │   ├── marketing_workflow.py     # 活动工作流提示词
│   │   └── templates.py              # 通用模板定义
│   ├── services/                     # 业务服务层
│   │   ├── __init__.py
│   │   ├── graph_run_service.py      # 图执行服务
│   │   └── skill_service.py          # 技能服务
│   ├── tools/                        # 工具函数
│   │   ├── __init__.py
│   │   └── function_call.py          # 函数调用工具
│   ├── utils/                        # 通用工具
│   │   ├── __init__.py
│   │   ├── file_reader.py            # 文件读取
│   │   ├── format_converter.py       # 格式转换
│   │   └── html_template.py          # HTML模板
│   ├── static/                       # 静态资源
│   │   ├── assets/                   # 编译后的资源
│   │   └── index.html                # 前端入口
│   ├── __init__.py
│   ├── config.py                     # 配置管理
│   └── main.py                       # 应用入口
├── data/                             # 数据目录
│   ├── uploads/                      # 上传文件存储
│   ├── skills.db                     # 业务数据库
│   └── checkpoints.db                # 状态持久化数据库
├── scripts/                          # 脚本目录
├── tests/                            # 测试目录
├── .env.example                      # 环境变量示例
├── pyproject.toml                    # 项目配置
└── requirements.txt                  # 依赖列表
```

## 文件用途详解

### 应用入口与配置

| 文件路径 | 用途说明 |
|----------|----------|
| `src/main.py` | **应用入口** - FastAPI 应用实例创建、中间件配置、路由注册、日志设置 |
| `src/config.py` | **配置管理** - 使用 Pydantic Settings 管理环境变量，提供统一的配置获取接口 |
| `pyproject.toml` | **项目配置** - 定义项目名称、版本、依赖、构建配置和代码规范 |
| `requirements.txt` | **依赖列表** - 列出所有项目依赖及其版本约束 |
| `.env.example` | **环境变量示例** - 提供环境变量配置模板，包含服务、数据库、OpenAI 配置 |

### 智能体层 (Agents)

| 文件路径 | 用途说明 |
|----------|----------|
| `src/agents/__init__.py` | **模块初始化** - 定义模块导出 |
| `src/agents/component_value_fetch.py` | **组件值获取** - 获取分析组件的参数值 |
| `src/agents/data_analysis.py` | **数据分析** - 执行具体的数据分析任务 |
| `src/agents/file_upload.py` | **文件上传** - 处理文件上传和解析 |
| `src/agents/finalize.py` | **结果汇总** - 汇总分析结果，生成最终响应 |
| `src/agents/format_conversion.py` | **格式转换** - 数据格式转换处理 |
| `src/agents/intent_recognition.py` | **意图识别** - 理解用户意图，分类请求类型 |
| `src/agents/marketing_data_fetch.py` | **活动数据获取** - 从银行系统获取活动数据 |
| `src/agents/marketing_report_synthesis.py` | **报告合成** - 综合分析结果生成完整报告 |
| `src/agents/report_generation.py` | **报告生成** - 生成格式化的分析报告 |
| `src/agents/report_validation.py` | **报告验证** - 验证报告内容的正确性和完整性 |
| `src/agents/template_matching.py` | **模板匹配** - 根据需求匹配合适的分析模板 |
| `src/agents/utils.py` | **智能体工具** - 智能体共用的工具函数 |

### API 接口层

| 文件路径 | 用途说明 |
|----------|----------|
| `src/api/__init__.py` | **模块初始化** |
| `src/api/routes.py` | **路由注册** - 统一注册所有 API 路由，创建主路由器 |
| `src/api/schemas.py` | **数据模型** - 使用 Pydantic 定义请求/响应的数据结构和验证规则 |
| `src/api/routers/__init__.py` | **路由模块初始化** |
| `src/api/routers/skills.py` | **技能管理路由** - 提供 SKILL 的 CRUD 接口（增删改查、分类管理） |
| `src/api/routers/files.py` | **文件处理路由** - 处理文件上传、下载、删除等操作 |
| `src/api/routers/analysis.py` | **分析任务路由** - 执行分析任务、查询分析结果、导出报告 |
| `src/api/routers/components.py` | **组件管理路由** - 管理分析组件的注册和查询 |

### 分析组件层

| 文件路径 | 用途说明 |
|----------|----------|
| `src/components/__init__.py` | **模块初始化** |
| `src/components/base.py` | **组件基类** - 定义分析组件的抽象基类，规范组件接口 |
| `src/components/overview.py` | **概览组件** - 提供数据概览分析功能的具体实现 |
| `src/components/registry.py` | **组件注册** - 管理所有分析组件的注册和发现机制 |

### 数据库层

| 文件路径 | 用途说明 |
|----------|----------|
| `src/db/__init__.py` | **模块初始化** |
| `src/db/models.py` | **数据模型** - 使用 SQLAlchemy ORM 定义数据库表结构（Skill、SkillCategory、AnalysisFramework 等） |
| `src/db/session.py` | **会话管理** - 创建和管理数据库连接会话，提供统一的数据库访问接口 |
| `src/db/seed.py` | **初始化数据** - 初始化默认分类、默认技能和默认分析框架的种子数据 |
| `data/skills.db` | **业务数据库** - SQLite 数据库文件，存储技能、分类、框架等业务数据 |
| `data/checkpoints.db` | **状态数据库** - LangGraph 状态持久化数据库，存储对话历史和任务状态 |

### LangGraph 智能体层

| 文件路径 | 用途说明 |
|----------|----------|
| `src/graph/__init__.py` | **模块初始化** - 定义模块导出，便于外部导入 |
| `src/graph/builder.py` | **图构建器** - 构建 LangGraph 工作流图，定义节点和边的连接关系 |
| `src/graph/checkpoint.py` | **状态持久化** - 配置 LangGraph 状态检查点，支持对话历史和任务状态持久化 |
| `src/graph/node_registry.py` | **节点注册** - 管理所有智能体节点的注册和发现机制 |
| `src/graph/planning.py` | **任务规划** - 负责将用户请求分解为子任务，制定执行计划 |
| `src/graph/state.py` | **状态定义** - 定义工作流执行过程中的状态数据结构 |
| `src/graph/supervisor.py` | **监督者节点** - 核心协调节点，负责任务分解、智能体调度和结果汇总 |

### 外部集成层

| 文件路径 | 用途说明 |
|----------|----------|
| `src/integrations/__init__.py` | **模块初始化** |
| `src/integrations/bank_marketing/__init__.py` | **活动模块初始化** |
| `src/integrations/bank_marketing/client.py` | **API 客户端** - 与活动系统对接的客户端 |
| `src/integrations/bank_marketing/mock_data.py` | **模拟数据** - 提供测试用的模拟数据 |
| `src/integrations/bank_marketing/schemas.py` | **数据模型** - 活动数据的数据结构定义 |

### 业务服务层

| 文件路径 | 用途说明 |
|----------|----------|
| `src/services/__init__.py` | **模块初始化** |
| `src/services/graph_run_service.py` | **图执行服务** - 封装 LangGraph 图的执行逻辑 |
| `src/services/skill_service.py` | **技能服务** - 封装技能相关的业务逻辑（分类管理、技能迁移、默认分类保护等） |

### 提示词模板

| 文件路径 | 用途说明 |
|----------|----------|
| `src/prompts/__init__.py` | **模块初始化** |
| `src/prompts/marketing_workflow.py` | **活动工作流** - 活动分析工作流的提示词模板 |
| `src/prompts/templates.py` | **通用模板** - 定义 LLM 调用的通用提示词模板 |

### 工具函数

| 文件路径 | 用途说明 |
|----------|----------|
| `src/tools/__init__.py` | **模块初始化** |
| `src/tools/function_call.py` | **函数调用** - 封装函数调用工具 |
| `src/utils/__init__.py` | **模块初始化** |
| `src/utils/file_reader.py` | **文件读取** - 支持 CSV、Excel 等文件格式的解析和数据提取 |
| `src/utils/format_converter.py` | **格式转换** - 实现不同数据格式之间的转换 |
| `src/utils/html_template.py` | **HTML 模板** - 定义报告的 HTML 模板结构 |

### 静态资源

| 文件路径 | 用途说明 |
|----------|----------|
| `src/static/index.html` | **前端入口** - 单页应用的 HTML 入口文件 |
| `src/static/assets/` | **编译资源** - 前端编译后的 CSS 和 JavaScript 文件 |

## 技术栈

| 分类 | 技术 | 版本 |
|------|------|------|
| 框架 | FastAPI | 0.115.0+ |
| 智能体 | LangGraph | 0.2.0+ |
| LLM | LangChain | 0.3.0+ |
| 数据库 | SQLAlchemy | 2.0+ |
| 数据分析 | Pandas | 2.0+ |
| 文件处理 | OpenPyXL / python-docx | - |
| 报告生成 | WeasyPrint | 62.0+ |

## 智能体节点说明

### 核心节点

| 节点名称 | 职责说明 |
|----------|----------|
| **Supervisor** | 核心协调节点，负责任务分解、智能体调度和结果汇总 |
| **IntentRecognition** | 理解用户意图，分类请求类型，决定下一步行动 |
| **DataAnalysis** | 执行具体的数据分析任务，支持多种分析维度 |
| **ReportGeneration** | 根据分析结果生成专业报告 |
| **ReportValidation** | 验证报告内容的正确性和完整性 |
| **Finalize** | 汇总分析结果，生成最终响应 |

### 辅助节点

| 节点名称 | 职责说明 |
|----------|----------|
| **FileUpload** | 处理文件上传和解析 |
| **MarketingDataFetch** | 从银行系统获取活动数据 |
| **ComponentValueFetch** | 获取分析组件的参数值 |
| **FormatConversion** | 数据格式转换处理 |
| **TemplateMatching** | 根据需求匹配合适的分析模板 |
| **MarketingReportSynthesis** | 综合分析结果生成完整报告 |

## 智能体状态流程

### 状态数据结构

系统使用 `AgentState` 作为智能体间传递的状态容器，定义于 `src/graph/state.py`：

| 字段名 | 类型 | 用途说明 |
|--------|------|----------|
| `messages` | `list[BaseMessage]` | 对话消息历史，支持累积追加 |
| `uploaded_file_path` | `str` | 用户上传文件的路径 |
| `file_preview` | `str` | 文件预览内容 |
| `analysis_framework` | `AnalysisFramework` | 分析框架配置（标题、组件列表、报告配置） |
| `sub_tasks` | `list[dict]` | 分解后的子任务列表 |
| `current_step` | `str` | 当前执行步骤 |
| `data_summary` | `str` | 数据汇总结果 |
| `per_component_results` | `dict` | 各分析组件的执行结果 |
| `html_report` | `str` | 生成的 HTML 报告内容 |
| `target_format` | `str` | 目标输出格式（HTML/DOCX） |
| `formatted_output_path` | `str` | 格式化输出文件路径 |
| `validation_result` | `str` | 报告验证结果 |
| `next_agent` | `str` | 下一个要执行的智能体名称 |
| `final_response` | `str` | 最终响应内容 |
| `plan` | `list[dict]` | 任务执行计划 |

### 状态流转流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                      状态流转流程图                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  START  ──►  Supervisor ──►  IntentRecognition                    │
│       │                              │                             │
│       │                              ▼                             │
│       │                    ┌─────────────────┐                     │
│       │                    │  MarketingData  │                     │
│       │                    │     Fetch       │                     │
│       │                    └────────┬────────┘                     │
│       │                             │                             │
│       │            ┌────────────────┼────────────────┐            │
│       │            ▼                ▼                ▼            │
│       │    TemplateMatching  ComponentValue   FileUpload          │
│       │         Fetch       Fetch                                 │
│       │            │                │                │            │
│       │            └────────────────┼────────────────┘            │
│       │                             ▼                             │
│       │                    ┌─────────────────┐                     │
│       │                    │   DataAnalysis  │                     │
│       │                    └────────┬────────┘                     │
│       │                             │                             │
│       │            ┌────────────────┼────────────────┐            │
│       │            ▼                ▼                ▼            │
│       │    ReportGeneration  ReportValidation  FormatConversion   │
│       │            │                │                │            │
│       │            └────────────────┼────────────────┘            │
│       │                             ▼                             │
│       │                    ┌─────────────────┐                     │
│       │                    │    Finalize     │                     │
│       │                    └────────┬────────┘                     │
│       │                             │                             │
│       └─────────────────────────────┴───► END                     │
│                                                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 状态流转详解

| 阶段 | 智能体 | 状态变化 | 对应代码文件 |
|------|--------|----------|--------------|
| **1. 意图识别** | `IntentRecognition` | 设置 `next_agent`、`plan`、`current_step` | `src/agents/intent_recognition.py` |
| **2. 数据获取** | `MarketingDataFetch` | 设置 `analysis_framework`、`data_summary` | `src/agents/marketing_data_fetch.py` |
| **3. 模板匹配** | `TemplateMatching` | 更新 `analysis_framework` | `src/agents/template_matching.py` |
| **4. 组件值获取** | `ComponentValueFetch` | 设置 `per_component_results` | `src/agents/component_value_fetch.py` |
| **5. 文件上传** | `FileUpload` | 设置 `uploaded_file_path`、`file_preview` | `src/agents/file_upload.py` |
| **6. 数据分析** | `DataAnalysis` | 更新 `per_component_results`、`data_summary` | `src/agents/data_analysis.py` |
| **7. 报告生成** | `ReportGeneration` | 设置 `html_report` | `src/agents/report_generation.py` |
| **8. 报告验证** | `ReportValidation` | 设置 `validation_result` | `src/agents/report_validation.py` |
| **9. 格式转换** | `FormatConversion` | 设置 `target_format`、`formatted_output_path` | `src/agents/format_conversion.py` |
| **10. 结果汇总** | `Finalize` | 设置 `final_response`，`next_agent = "__end__"` | `src/agents/finalize.py` |

### 状态路由机制

状态流转由 `Supervisor` 节点通过 `next_agent` 字段控制：

1. **路由决策**：`supervisor_router` 函数读取 `state["next_agent"]` 决定下一个执行节点
2. **循环执行**：所有子智能体执行完成后返回 `Supervisor`，直到 `next_agent = "__end__"`
3. **终止条件**：`Finalize` 节点设置 `next_agent = "__end__"` 时，流程终止

### 核心代码文件

| 文件路径 | 职责说明 |
|----------|----------|
| `src/graph/state.py` | 定义 `AgentState` 状态数据结构 |
| `src/graph/builder.py` | 构建 LangGraph 工作流，配置状态流转规则 |
| `src/graph/supervisor.py` | 监督者节点，负责任务调度和路由决策 |
| `src/graph/node_registry.py` | 注册所有智能体节点和路由函数 |
| `src/graph/checkpoint.py` | 状态持久化，支持对话历史保存 |

## 状态持久化

系统使用 SQLite 进行状态持久化，支持：
- 任务状态追踪
- 对话历史保存
- 分析结果缓存

## 开发指南

### 添加新的智能体节点

1. 在 `src/agents/` 目录下创建新智能体文件
2. 实现智能体逻辑（继承基础类或实现标准接口）
3. 在 `src/graph/node_registry.py` 中注册节点
4. 在 `src/graph/builder.py` 中配置节点连接

### 添加新的分析组件

1. 在 `src/components/` 目录下创建新组件
2. 继承 `BaseComponent` 基类
3. 实现 `execute()` 方法
4. 在 `src/components/registry.py` 中注册组件

### 添加新的 API 路由

1. 在 `src/api/routers/` 目录下创建新路由文件
2. 定义路由函数
3. 在 `src/api/routes.py` 中注册路由

## 部署说明

### 生产环境部署

```bash
# 安装依赖（生产模式）
pip install -e . --no-dev

# 使用 gunicorn 启动
gunicorn src.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Docker 部署

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY pyproject.toml requirements.txt ./
RUN pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## 安全注意事项

1. 配置适当的 CORS 策略
2. 对上传文件进行类型和大小限制
3. 使用环境变量管理敏感配置
4. 对用户输入进行严格验证
5. 定期备份数据库

## 许可证

MIT License

## 联系方式

如有问题或建议，请联系开发团队。

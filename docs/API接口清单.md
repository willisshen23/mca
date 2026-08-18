# API 接口清单

> 统计范围：后端正式接口（`backend/src`），**不含 `mock/` 目录**下的模拟接口。
> 后端入口：[backend/src/main.py](../backend/src/main.py)，所有业务接口统一挂载在 `/api` 前缀下；路由定义位于 [backend/src/api/routers/](../backend/src/api/routers/)。
> 分类依据：前端实际调用方 —— `/chat-ui` 独立聊天页（前台） vs 管理后台各页面（`/management`、`/skills`、`/history`、`/conversation-logs`、`/templates`、`/logs`、`/settings`）。
> 更新日期：2026-08-05

## 接口统计

| 分类 | 数量 |
|---|---|
| 前台接口（聊天页 `/chat-ui`） | 17 |
| 管理后台接口 | 38 |
| **合计** | **55** |


管理后台 38 个接口分布：用量看板 2、运行历史 6、会话日志 2、技能管理 8、活动模板 5、系统设置 11、日志查看 4。

> 统计口径：同一路径的不同 HTTP 方法（如 GET/POST `/api/skills`）按 2 个接口计。

## 一、前台接口（聊天页 UiChatView，`/chat-ui`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v2/agent/run` | 发起 agent 对话（SSE 流式） |
| POST | `/api/v2/agent/cancel` | 取消运行 |
| POST | `/api/v2/agent/resume` | 人工确认后恢复运行 |
| GET | `/api/conversations` | 会话列表 |
| POST | `/api/conversations` | 新建会话 |
| GET | `/api/conversations/{thread_id}` | 会话消息详情 |
| PATCH | `/api/conversations/{thread_id}` | 重命名会话 |
| DELETE | `/api/conversations/{thread_id}` | 删除会话 |
| POST | `/api/upload` | 上传文件（聊天附件） |
| GET | `/api/download/{file_name}` | 下载文件 |
| GET | `/api/report-exports/{file_name}` | 下载报告导出文件（SSE 产物 download_url） |
| POST | `/api/reports/html` | 生成/保存 HTML 报告 |
| GET | `/api/quick-prompts` | 聊天页快捷提问列表 |
| POST | `/api/agent-run-history/{request_id}/feedback` | 报告点赞/点踩反馈 |
| POST | `/api/agent-run-history/thread/{thread_id}/feedback` | 按会话提交反馈 |
| GET | `/api/agent-run-history/{history_id}/report` | 报告卡片下载 |
| POST | `/api/usage-dashboard/events` | 前端埋点事件上报 |

前端调用来源：`frontend/src/api/` 下的 [agentRun.js](../frontend/src/api/agentRun.js)、[conversations.js](../frontend/src/api/conversations.js)、[files.js](../frontend/src/api/files.js)、[agentRunHistory.js](../frontend/src/api/agentRunHistory.js)、[usageDashboard.js](../frontend/src/api/usageDashboard.js)、[quickPrompts.js](../frontend/src/api/quickPrompts.js)。

## 二、管理后台接口

### 2.1 用量看板（HomeView，`/management`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/usage-dashboard/summary` | 用量汇总 |
| GET | `/api/usage-dashboard/export` | 用量明细导出（xlsx） |

### 2.2 运行历史（HistoryView，`/history`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/agent-run-history` | 运行记录列表 |
| GET | `/api/agent-run-history/export` | 运行记录导出 |
| GET | `/api/agent-run-history/sessions` | 报告会话列表 |
| GET | `/api/agent-run-history/sessions/export` | 会话导出 |
| GET | `/api/agent-run-history/sessions/{thread_id}` | 会话详情 |
| GET | `/api/agent-run-history/{history_id}` | 单条记录详情 |

### 2.3 会话日志（ConversationLogsView，`/conversation-logs`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/conversation-logs` | 日志列表 |
| GET | `/api/conversation-logs/thread/{thread_id}` | 单会话轮次 |

### 2.4 技能管理（SkillManagementView `/skills`、SkillComposerView `/analysis/compose`、TemplateView `/templates`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/api/skills` | 技能列表 / 新建 |
| PATCH / DELETE | `/api/skills/{skill_id}` | 修改 / 删除技能 |
| GET / POST | `/api/skill-categories` | 分类列表 / 新建 |
| DELETE | `/api/skill-categories/{category_id}` | 删除分类 |
| PATCH | `/api/skills/{skill_id}/category` | 调整技能分类 |

### 2.5 活动模板（TemplateView，`/templates`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/api/activity-templates` | 模板列表 / 新建 |
| PATCH / DELETE | `/api/activity-templates/{template_id}` | 修改 / 删除 |
| POST | `/api/activity-templates/{template_id}/apply` | 应用模板 |

### 2.6 系统设置（SettingsView，`/settings`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/api/system-prompts` | 提示词列表 / 新建 |
| GET | `/api/system-prompts/key/{prompt_key}` | 按 key 查询提示词 |
| GET | `/api/system-prompts/{prompt_id}` | 按 id 查询提示词 |
| PATCH | `/api/system-prompts/{prompt_id}` | 修改提示词 |
| POST | `/api/system-prompts/{prompt_id}/publish` | 发布提示词 |
| GET / PATCH | `/api/env-config` | 查看 / 修改环境配置 |
| POST | `/api/env-config/restart` | 重启后端 |
| GET / PUT | `/api/quick-prompts/admin` | 快捷提问的后台管理 |

### 2.7 日志查看（LogsView，`/logs`）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/logs/files` | 日志文件列表 |
| GET | `/api/logs/content` | 日志内容 |
| GET | `/api/logs/tail` | 日志实时尾部 |
| GET | `/api/logs/download/{filename}` | 日志下载 |


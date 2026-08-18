# openJiuwen agent-core 替换 langgraph / deepagents 迁移调研

> 日期：2026-08-07
> 结论先行：**可行，且 HITL/中断恢复/流式三大核心机制有一一对应物；但"审批 edit 决策"、"SQLite checkpointer"、"context 注入"、"多模型中间件路由"四处需要自研胶水层。最大风险是 agent-core 自身仍是 0.x（PyPI 最新 0.1.16.post2）且依赖沉重（pymilvus/transformers 等），离线部署包需重做。**

---

## 1. 本项目现状：对 langgraph / deepagents 的依赖点

agent_v2 是唯一运行时（v1 已废弃）。依赖版本（backend/requirements.txt）：
`langgraph>=1.2,<2.0`、`langgraph-checkpoint-sqlite>=2.0,<4.0`、`deepagents==0.6.12`（钉版）、`langchain>=1.3.11`、`langchain-anthropic` / `langchain-google-genai`（deepagents 硬依赖）。

| # | 依赖点 | 位置 | 具体用法 |
|---|--------|------|----------|
| 1 | DeepAgent 组装 | `backend/src/agent_v2/agent_factory.py` | `create_deep_agent(model, tools, system_prompt, middleware, state_schema, context_schema, checkpointer, interrupt_on)` 进程级单例 |
| 2 | 中间件×3 | `agent_factory.py`、`routing/model_router.py` | `TieredModelMiddleware`（按轮选模型）、`ToolGovernanceMiddleware`（工具白名单，剥离 execute/fs/task）、`ToolCallLimitMiddleware`（每轮≤8 次工具调用） |
| 3 | 图状态 + reducer | `state/schema.py` | `AgentV2State(DeepAgentState)`：`messages`(add_messages)、`analysis_queue`/`activity_list`(merge_activity_list)、`report_context`/`html_report` 等(_last_wins)；曾踩 DeltaChannel 坑已覆盖回 add_messages |
| 4 | 敏感参数注入 | `state/schema.py` `AgentV2Context`、`state/request_context.py` | user_id/org_no/channel/file_path 只经 `graph.astream(context=...)` + ContextVar 注入，不进 LLM；工具内经 `ToolRuntime.context` 读取 |
| 5 | SQLite checkpointer | `state/persistence.py` | `AsyncSqliteSaver` 连 `checkpoints.db`（与旧图共享文件、独立连接、busy_timeout=5s）；会话重载链路（`api/routers/conversations.py`）从最新 checkpoint 的 `channel_values["messages"]` 读历史 |
| 6 | HITL 审批 | `agent_factory.py` `_INTERRUPT_ON`、`runtime.py` `stream_agent_resume` | 写工具 `interrupt_on` 硬中断，decisions = approve/edit/reject；resume 用 `Command(resume={"decisions":[...]})`；流中出现 `__interrupt__` |
| 7 | SSE 桥接 | `events/sse_bridge.py`、`runtime.py` | `graph.astream` 事件 → SSE 帧；`_BufferedRun` 支持断线重连回放；取消注册表在流事件间隙生效；generate_report 的内部管线进度帧抑制 |
| 8 | 业务工具×11 | `tools/` | search_activities / get_activity_detail / get_available_templates / generate_report / add/remove/update_analysis_queue / parse_uploaded_data / get_report_content / modify_report / export_report + 内置 `write_todos` |
| 9 | 报告管线旧图 | `backend/src/report_pipeline/state.py` | 9 节点 langgraph StateGraph，被 `generate_report` 工具复用（决策#5：原样复用） |

ops-assistant（ops/ 独立服务 :9100）不依赖 langgraph/deepagents，不在本次迁移范围。

## 2. openJiuwen agent-core 能力调研（一手来源）

openJiuwen 是华为云 AgentArts 的开源版（2025-12 开源），agent-core 是其 Python SDK 核心引擎。**License: Apache-2.0**；**Python 要求 >=3.11,<3.14**（本项目 3.12 ✓）；安装 `pip install -U openjiuwen`，PyPI 最新 **0.1.16.post2**（0.x，迭代极快，0.1.x 已发 25 个版本）。

来源：README https://github.com/openJiuwen-ai/agent-core ；PyPI https://pypi.org/pypi/openjiuwen/json

### 2.1 智能体与图编排

- **ReActAgent**：`ReActAgent(card=AgentCard(...)).configure(ReActAgentConfig(model_config_obj, model_client_config, prompt_template))`；`Runner.run_agent(agent, {"query": ..., "conversation_id": ...})` 驱动「思考→行动→观察」循环。
  来源：docs/zh/2.开发指南/智能体/构建ReActAgent.md
- **Workflow**：`Workflow()` + `set_start_comp/add_workflow_comp/set_end_comp` + `add_connection`；`BranchComponent.add_branch("${num} <= 30", [...])` 条件分支；组件为 `WorkflowComponent.invoke(inputs, session, context)`。组件并发执行、流式传值、动态跳转均为内置。
  来源：docs/zh/2.开发指南/高阶用法/Session/状态管理.md、README
- **多智能体**：AgentAsTool（子 Agent 作为工具挂到主 Agent 的 ability_manager）、TeamRuntime/BaseTeam。
  来源：docs/zh/2.开发指南/多智能体/

### 2.2 工具机制

三种工具形态：`@tool` 装饰器（本地函数）、`RestfulApi`（HTTP 接口）、`MCPTool`（MCP）。注册：`Runner.resource_mgr.add_tool(t)` + `agent.ability_manager.add(t.card)`。
来源：docs/zh/2.开发指南/基础功能/自定义工具.md

### 2.3 HITL（对本项目最关键）

基于 **Rail 拦截器**，不改 Agent 主流程：

- `ConfirmInterruptRail(tool_names=[...])`：拦截指定工具 → `Runner.run_agent` 返回 `result_type="interrupt"` + `interrupt_ids` + `state`（含 tool_name/tool_args/payload_schema）→ 用户经 `InteractiveInput().update(tool_call_id, {"approved": bool, "feedback": str, "auto_confirm": bool})` 回答 → 同 `conversation_id` 再次 `run_agent` 恢复。
- 流式场景：`Runner.run_agent_streaming` 产出 `type='__interaction__'` 的 OutputSchema，再次流式调用恢复。
- **自定义 Rail**：继承 `BaseInterruptRail`/`ConfirmInterruptRail` 实现 `resolve_interrupt`，三种决策 `ApproveResult / RejectResult / InterruptResult`；官方明示 ApproveResult 场景含「需要修改参数」——即 **edit 决策可用自定义 Rail 实现**（approve 时改写 tool_args）。
- 子 Agent 中断自动向父 Agent 传播；`auto_confirm` 存 Session 且随持久化。
- 另有 `AskUserRail`（主动提问补全信息）。
来源：docs/zh/2.开发指南/高阶用法/人机交互.md

### 2.4 Session：状态 / 持久化 / 流式 / 中断恢复

- 统一执行引擎：全局状态 `get/update_global_state` + 组件私有状态 `get/update_state`；中断时自动快照、同 session_id 重跑即从断点续跑（含异常中断恢复）。
- 流式：`session.write_stream(OutputSchema)` / `write_custom_stream(dict)`；消费端 `workflow.stream(..., stream_modes=[OUTPUT, CUSTOM])`。
- Checkpointer：`CheckpointerFactory` 可插拔 provider 注册机制；内置 **in_memory**；扩展仓提供 **Redis checkpointer**（`openjiuwen/extensions/checkpointer/redis`）；`persistence.py` 有基于 SQLAlchemy + KV 抽象的 `BaseStorage`。**未见开箱即用的 SQLite checkpointer**。
- 内置全链路 tracer（调测/可观测）。
来源：docs/zh/2.开发指南/高阶用法/Session/{概述,中断恢复,流式输出,状态管理}.md；仓库 openjiuwen/core/session/checkpointer/

### 2.5 模型接入

`ModelClientConfig(client_provider, api_base, api_key, custom_headers, verify_ssl)` + `ModelRequestConfig(model, temperature, top_p)`；内置 provider：**OpenAI（兼容协议，可指任意 api_base）与 SiliconFlow**；支持自定义请求头（多租户/网关场景）。`Model.invoke/stream` 均异步，tool calling 走标准 JSON Schema。
来源：docs/zh/2.开发指南/基础功能/接入大模型.md

### 2.6 依赖负担

`requires_dist`：aiohttp、sqlalchemy[asyncio]、sqlmodel、openai、**transformers、tiktoken、dashscope、pymilvus**、fastmcp、trafilatura、pdfplumber 等 —— 比 langchain 栈更重，离线 wheel 集需在 ky10/Python3.12 机器重做。

## 3. 能力映射表

| 本项目（langgraph/deepagents） | agent-core 对应物 | 判定 |
|---|---|---|
| `create_deep_agent` 主循环 | `ReActAgent` + `ReActAgentConfig` + `Runner.run_agent` | ✅ 直接替代（规划/todos 见下） |
| 业务工具（langchain StructuredTool + ToolRuntime 注入） | `@tool` + `ability_manager.add(card)`；注入改走 ContextVar（框架无关，可保留） | 🔶 工具签名需改造（inputs dict + session） |
| `interrupt_on` approve/reject | `ConfirmInterruptRail` | ✅ 直接替代 |
| `interrupt_on` **edit**（改参数后执行） | 自定义 Rail（`resolve_interrupt` → ApproveResult 改写 args） | 🔶 需自研胶水（官方支持该模式） |
| `AsyncSqliteSaver` | in_memory 内置 / Redis 扩展 / 自研 SQLAlchemy provider | 🔶 无 SQLite 开箱版；行内若无 Redis 需自研 provider（工厂已可插拔） |
| `AgentV2State` + reducer 通道 | Session 全局/组件状态（无 reducer 概念，写后组件结束生效） | 🔶 范式不同：状态合并逻辑要搬进工具/组件代码 |
| `AgentV2Context` context 注入 | 无直接对应；ContextVar 兜底链路框架无关可保留 | 🔶 保留 ContextVar 方案即可 |
| `graph.astream` → sse_bridge | `Runner.run_agent_streaming` / `session.stream_iterator` 产出 OutputSchema/CustomSchema | ✅ 机制等价，桥接层重写 |
| `__interrupt__` 流帧 | `type='__interaction__'` 流帧 | ✅ 直接替代 |
| `TieredModelMiddleware`（按轮选模型） | 无；每 Agent 一个 model_client_config | 🔶 需自定义 Controller/Agent（文档有「构建自定义智能体」）或按工具内 `Model` 直调 |
| `ToolGovernanceMiddleware` 白名单 | 不需要——agent-core 默认不挂载任何内置工具 | ✅ 治理问题消失 |
| `ToolCallLimitMiddleware`（8 次/轮） | 未见内置（未找到一手证据） | 🔶 需自研（自定义 Rail 计数即可） |
| `write_todos` 规划辅助 | 无内置（未找到一手证据） | 🔶 小工具自研（写 Session 全局状态） |
| 报告管线 9 节点 StateGraph | `Workflow` + 组件 + `BranchComponent` | ✅ 可迁；也可短期保留 langgraph 仅限此图 |
| deepagents task 子代理（已剥离） | AgentAsTool / TeamRuntime | ➖ 本项目已禁用，无迁移需求 |
| 会话重载读 checkpoint messages | Session 状态结构不同，conversations.py 重载链路需重写 | 🔶 重写（但摆脱了 DeltaChannel 类坑） |

## 4. 迁移方案建议（分阶段）

- **P0 技术验证 spike（1~2 天）**：venv 装 `openjiuwen==0.1.16.post2`；验证①行内 deepseek 端点（OpenAI 兼容 + tool calling）经 `ModelClientConfig(client_provider="OpenAI", api_base=...)` 可用；②ReActAgent + 1 个写工具 + ConfirmInterruptRail 走完 interrupt → InteractiveInput resume 全流程；③ `run_agent_streaming` 产出可桥接 SSE。**任何一条不过即中止，成本可控。**
- **P1 替换对话运行时**：agent_v3 包并行新建（不动 agent_v2）；11 个业务工具包一层 `@tool`（函数体复用，ContextVar 注入保留）；自定义 `ApprovalEditRail` 实现 approve/edit/reject 三决策；sse_bridge 改为消费 OutputSchema/CustomSchema；`_BufferedRun`/取消注册表/审计层（runtime.py 大半）框架无关，平移。沿用双开关策略新增 `AGENT_V3_ENABLED`。
- **P2 持久化**：行内有 Redis → 直接用扩展 checkpointer；没有 → 基于 `CheckpointerFactory.register` 自研 SQLite/MySQL provider（参考 `persistence.py` 的 BaseStorage）。同步重写 conversations.py 会话重载。
- **P3 报告管线**：generate_report 内嵌的 9 节点旧图迁 Workflow 组件，或决策保留 langgraph 仅限该图（依赖面大幅缩小但仍残留）。建议迁，彻底摘除 langgraph。
- **P4 收尾**：离线 wheel 集重做（ky10/py3.12 `pip download openjiuwen`）；删 deepagents/langchain-anthropic/langchain-google-genai；回归 77 例 pytest 中框架相关用例重写。

## 5. 风险与未知数

1. **框架成熟度**：agent-core 自身 0.1.x、发布节奏极快（与 deepagents 0.6.12 同类风险，但华为背书+Apache-2.0+政企同源，可持续性好于 deepagents 个人/小团队维护）。接口钉版策略必须沿用。
2. **edit 决策非原生**：三决策语义需自定义 Rail 严格复刻（含 reject 的 feedback 作为 ToolMessage 回传——官方文档确认支持）。
3. **无 SQLite checkpointer 开箱版**：银行内网未必有 Redis；自研 provider 的工作量与正确性（并发写、busy_timeout 等价物）是 P2 主要风险。
4. **状态范式差异**：reducer 通道（并行工具写同键合并）在 Session 模型下无对应，`merge_activity_list` 语义需在工具内自行保证（本会话语境下并行写同一键的场景本就有限，风险中低）。
5. **依赖体积**：transformers/pymilvus/trafilatura 等对离线部署包体积与 ky10 兼容性是实际负担；需验证能否裁剪（extras 或排除）。
6. **多模型路由**：`TieredModelMiddleware` 无对应，需自定义 Controller；工具内 `get_llm()` 分角色可平移为工具内直构 `Model`。
7. **未验证项（一手资料未覆盖）**：ReActAgent 的最大迭代/工具调用上限配置项；长会话上下文裁剪策略；token 级流式在 interrupt 前后的完整性。这些在 P0 spike 中必须实测。

## 附：本项目已验证、迁移时无需重验的事实

- 行内 deepseek-v4-flash 端点 tool calling 可用（M1 验收记录）——P0 直接复用该端点配置。
- `from __future__ import annotations` 曾破坏 langchain 工具注入（M1 坑）；迁 agent-core 后该坑自然消失，但新框架的注解处理需在 spike 期顺手验证。

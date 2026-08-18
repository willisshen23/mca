# openJiuwen 迁移 P3 设计：依赖摘除与 v2 退役

> 日期：2026-08-10
> 前置：调研 `2026-08-07-openjiuwen-agent-core-migration-research.md` §4 P3/P4；P2 验收 `2026-08-10-agent-v3-p2-acceptance.md`
> 已批准决策（2026-08-10 与用户对齐）：**① 不迁 Workflow 组件，P3 = 依赖摘除；② LLM 客户端也迁 openjiuwen Model（langchain 全系删）；③ v2 在 P3 内退役（删 agent_v2 包 + AGENT_V3_ENABLED 开关）；④ 方案一一次性切换**

## 1. 目标与范围

**目标**：彻底摘除 langgraph/langchain/deepagents 依赖，v3 成为唯一运行时，依赖面收敛到 openjiuwen 单框架。

- **In scope**：
  1. 工具实现层中立化：8 个 v2 工具模块的函数体（12 个业务工具）移出 agent_v2，剥掉 langchain 壳（`@tool`/`ToolRuntime`/`Command`）；
  2. LLM 层 `get_llm` → `get_model`（openjiuwen Model），4 个管线节点 + report_modify 异步化；
  3. 删 `agent_v2/` 包、`AGENT_V3_ENABLED` 开关、conversations.py 的 langgraph checkpoint 清理；
  4. requirements 删除 langgraph/langchain/langchain-core/langchain-openai/langgraph-checkpoint-sqlite/deepagents/langchain-anthropic/langchain-google-genai 共 8 条；
  5. 测试同步（删 agent_v2 专属测试、迁移纯业务用例、重写框架相关用例）。
- **Out of scope**：管线迁 Workflow 组件（已决策不做——管线自 M3 起就是纯 Python 顺序编排，无图可迁）；`agent_v3` 包改名（配置/文档兼容，纯 churn）；MySQL checkpointer（conf 已预留）；分层模型路由（v2 model_router 随包删除，v3 主模型已是唯一在用的，无需求）；ops-assistant（无 langchain 依赖，不动）；离线 wheel 集重做（依赖删除后随下次发版处理）。

## 2. 关键事实（源码已核实）

1. **管线早已不是图**：`agent_v2/tools/report_gen.py` 的 `run_report_pipeline` 是纯 Python 顺序编排（`step()` 逐个调 capability 节点函数 + html_guard 重试循环），运行时不经过 langgraph 调度。
2. **v3 运行时路径上的框架残留**（全部清单）：
   - `langgraph.types.Command`：8 个 v2 工具模块函数体的返回契约，v3 壳（`agent_v3/tools/__init__.py` invoke_v2_tool）翻译它；
   - `langgraph.config.get_stream_writer`：report_gen 进度帧来源，v3 靠 `patch_report_gen_writer` 进程级 patch 注入；
   - langchain `@tool`/`ToolRuntime`：v2 工具装饰层，v3 壳用 duck-type SimpleNamespace 假 runtime 绕过；
   - `add_messages`/`BaseMessage`：`report_pipeline/state.py`（仅类型标注，运行时是 plain dict）、`services/agent_run_history_service.py`（`_original_user_text` 解析，已兼容 dict）；
   - `ChatOpenAI`（`config.py get_llm`）：**唯一真实运行时依赖**，调用方 = 4 个管线节点（template_matching / component_value_fetch / activity_template_matching / marketing_report_synthesis）+ `report_modify` + `utils/llm_logging`；agent_v2 包内（agent_factory/model_router）随包删除。
3. **openjiuwen Model 接口**（`core/foundation/llm/model.py`）：`Model(ModelClientConfig, ModelRequestConfig)`；`await model.invoke(messages: str | list, *, tools, temperature, max_tokens, timeout, ...) -> AssistantMessage`（有 `.content`，节点现有 `response.content` + `extract_json` 解析零改动）。
4. **管线执行模型**：generate_report 在 async 工具体内 `asyncio.to_thread(run_report_pipeline, seed, writer)`——整条管线跑在 worker 线程，同步 DB/HTTP 不阻塞主事件循环；`writer` 在主循环抓取后闭包传入线程。
5. **token_budget / llm_logging 耦合**：`utils/token_budget.py` 的守卫挂在 ChatOpenAI 实例上（`configure_token_budget`，超限抛 `ModelContextLengthExceeded`）；`utils/llm_logging.py` 是 langchain `BaseCallbackHandler`（`LLMIOCharLogger`）。两者都需在 openjiuwen Model 上重建。
6. **v2 外部引用面**（删包前必须先移走的）：`agent_v2/prompts/`（build_system_prompt 被 v3 agent_factory 用；perspectives 被 report_gen 用）、`agent_v2/state/request_context.py`（ContextVar，被 v3 runtime/tools 用）、`agent_v2/tools/`（8 个业务模块 = 12 个业务工具的实现本体）、`agent_v2/tools/_common.py`（activity_key 等 helper，v3 sse_bridge 也用）。
7. **ops/ 服务零 langchain 依赖**；tests/agent_v2 约 20 个测试文件中纯业务用例（seed/pipeline/工具逻辑）需迁移，hitl/sse_bridge/model_router 等 v2 专属删除。
8. **前端契约不动**：HTTP 前缀 `/api/v2/agent/*` 保留（仅内部实现切换）；`AGENT_V3_ENABLED` 删除后 v3 路径成为唯一分支。

## 3. 目标架构

```
┌─ agent_v3（唯一运行时）──────────────────────────┐
│ runtime.py ── sessions.py ── state/persistence.py │
│ agent_factory.py（ReActAgent + Rails）            │
│ tools/                                            │
│   ├─ __init__.py   openjiuwen @tool 壳（变薄）     │
│   └─ impl/         业务实现（中立，无框架依赖）     │
│        ├─ ToolContext(state/request/stream_writer)│
│        └─ ToolOutcome(content, state_updates)     │
├─ report_pipeline/（保持中立包）────────────────────┤
│   capabilities/*.py  async 化，get_model 取 LLM    │
│   state.py           去掉 add_messages/BaseMessage │
├─ src/llm.py（新）─────────────────────────────────┤
│   get_model(role) → GuardedModel(openjiuwen Model)│
│   token_budget 守卫 + io 日志在此重建              │
└───────────────────────────────────────────────────┘
删除：agent_v2/ 全包、langgraph/deepagents/langchain 全系
```

## 4. 组件设计

### 4.1 工具实现层（`agent_v3/tools/impl/`）

- `ToolContext` dataclass：
  - `state: dict`——会话状态快照（现有 `_SESSION_STATE_KEYS` 七键 + turn 级两键，口径不变）；
  - `request: dict`——现 request_context ContextVar 内容（user_id/user_name/org_no/src_sys_no/channel/thread_id/request_id/original_user_text/uploaded_file_path）；
  - `tool_call_id: str`；
  - `write_stream: Callable[[dict], None]`——进度帧回调，**显式注入**（v3 壳桥 `session.write_custom_stream`；`patch_report_gen_writer` hack 删除）。
- `ToolOutcome` dataclass：`content: str` + `state_updates: dict`，替代 langgraph `Command`。
- 8 个实现模块（activity_query / analysis_queue / data_parse / template / skill / report_gen / report_modify / report_export，共 12 个业务工具；write_todos 为 v3 原生无此问题）从 v2 平移函数体：签名末尾 `runtime: ToolRuntime` → `ctx: ToolContext`；`resolve_state/resolve_context` 改为从 ctx 直取；`tool_command(content, tool_call_id, updates)` → `ToolOutcome(content, updates)`。
- `_common.py` helper（activity_key/activity_name/error_content/ok_content/summarize/is_timeout_exception/is_context_length_exception 等）随 impl 平移。
- v3 `@tool` 壳变薄：构造 ToolContext → 调 impl → 把 `state_updates` 写进 session。不再有伪造 langchain runtime 的适配逻辑。
- `report_gen` 内 `writer = get_stream_writer()` → `ctx.write_stream`。

### 4.2 LLM 层（`src/llm.py` 新建）

- `get_model(role: str = "report_generation", temperature: float = 0.1) -> GuardedModel`：
  - 角色配置读现有 `settings.{role}_llm_*` 字段（api_key/base_url/model/max_tokens，缺省回退全局 `llm_*`——与 get_llm 同语义、同实例缓存策略）；
  - 构 `ModelClientConfig(client_provider="OpenAI", ...)` + `ModelRequestConfig`（参考 `agent_v3/agent_factory.build_v3_model_configs`）。
- `GuardedModel`（薄 wrapper，组合 openjiuwen Model）：
  - `async invoke(messages) -> AssistantMessage`：invoke 前做 token_budget 计数，超限抛 `ModelContextLengthExceeded`（异常类型不变，`is_context_length_exception` 现有判定不动）；
  - 内联 io 日志（prompt/response 字符数，对齐 LLMIOCharLogger 现有输出格式；或桥接 openjiuwen `LLMCallEvents` 回调——实施时以行为等价为准二选一）。
- 调用点改造（5 处）：4 个管线节点 + report_modify，`llm.invoke(prompt).content` → `(await model.invoke(prompt)).content`。
- **异步化**：9 个 capability 节点函数与 `run_report_pipeline` 改 async；generate_report impl 内 `asyncio.to_thread(run_report_pipeline, seed, writer)` → `await asyncio.to_thread(lambda: asyncio.run(run_report_pipeline(seed, writer)))`——管线仍在 worker 线程的独立事件循环里跑，同步 DB/HTTP 不进主循环（语义与今天等价），LLM 调用在该循环内真异步。
- `config.py` 删除 `get_llm`/`_build_llm`/`ChatOpenAI` 及 langchain import；角色 settings 字段保留。

### 4.3 删除清单

| 删除项 | 前置动作 |
|---|---|
| `agent_v2/runtime.py`、`agent_factory.py`、`events/`、`state/persistence.py`、`state/schema.py`、`routing/` | 无（v3 已有对应物） |
| `agent_v2/prompts/` | build_system_prompt / perspectives 先挪 agent_v3（或中立包） |
| `agent_v2/state/request_context.py` | 先挪 agent_v3 |
| `agent_v2/tools/`（8 业务模块 + _common） | 函数体平移进 impl/ 后删 |
| `AGENT_V3_ENABLED` 配置项 | routers/agent_v2.py 直挂 v3 runtime；main.py lifespan 去开关 |
| conversations.py `_get_checkpoint_saver` + DELETE 内 langgraph 清理 | v2 checkpoint 不再有人写（`data/checkpoints.db` 成历史文件，代码不再引用） |
| requirements 8 条（langgraph、langchain、langchain-core、langchain-openai、langgraph-checkpoint-sqlite、deepagents、langchain-anthropic、langchain-google-genai） | 上述全部完成后 |
| tests/agent_v2 专属（hitl/sse_bridge/model_router/runtime_config 等） | 纯业务用例（seed/pipeline/工具逻辑）先迁出 |

## 5. 错误处理

- 超上下文：`GuardedModel` 抛 `ModelContextLengthExceeded`（类型不变）→ 节点/工具现有 `is_context_length_exception` 分支 → `MODEL_BUSY_MESSAGE`。
- 超时：openjiuwen timeout 异常按实测类型扩充 `is_timeout_exception` 判定 → 现有"大模型访问超时"文案。
- 模型调用失败（如 181001）：沿用现有 "ERROR:" 前缀工具结果约定。
- **风险登记**：openjiuwen Model 的 max_tokens/timeout/重试行为与 ChatOpenAI 不完全等价——**实施第一步先跑 get_model spike**（对行内 deepseek 端点验证：普通调用、长输出、超时生效、错误类型、并发）；关键项不过则回退为保留 langchain-openai（方案二路径），其余摘除继续。

## 6. 测试策略

- **保留**：report_pipeline 节点测试、seed_builder、report 系列等框架无关用例（节点异步化后同步加 await/事件循环适配）。
- **迁移**：tests/agent_v2 纯业务用例 → tests/agent_v3 或 tests/report_pipeline。
- **删除**：v2 专属（hitl/sse_bridge/model_router/runtime_config/state_concurrent_writes/tool_runtime_injection 等）。
- **重写**：test_llm_logging（按 GuardedModel 实现）；tests/agent_v3/test_v3_tool_adapter.py（假 runtime 适配器不存在了，改为 ToolContext 契约测试）。
- **新增**：get_model 工厂配置正确性；GuardedModel 超限/日志；impl 层 ToolContext/ToolOutcome 契约。
- **验收**：全量 pytest + P1/P2 实机联调清单回归（重点：报告生成全流程含进度帧、modify_report、export_report、审批三决策、重启续聊）。

## 7. 风险

1. **openjiuwen Model 行为差**（超时/截断/重试/错误类型）——spike 先行，见 §5。
2. **变更面大**：一次性删 v2 + 换 LLM 层，回归依赖既有 300 例测试网 + P1/P2 联调清单；节点异步化注意 sync I/O 不得漏进主循环。
3. **pickle 兼容**：v3_checkpoints.db 里旧 blob 的 state 若引用 langchain 类型（如 pipeline 曾写入 HumanMessage 进会话 state），删包后反序列化失败——框架容错为"上下文重来"（历史展示不受影响，业务表驱动），可接受；实施时核实会话 state 七键确无 langchain 对象。

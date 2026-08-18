# P0 技术验证 spike 报告：openJiuwen agent-core 替换 langgraph/deepagents

> 日期：2026-08-07
> 依据：`docs/superpowers/specs/2026-08-07-openjiuwen-agent-core-migration-research.md` 第 4 节 P0 阶段
> 代码：`spikes/openjiuwen-p0/`（t1~t4，venv `.venv`，openjiuwen==0.1.16.post2，Python 3.12.2）
> 端点：复用 `backend/.env`（`https://api.deepseek.com` / `deepseek-v4-flash`，M1 已验收 tool calling）

## 总结论：**P0 三项验证全部通过，可进入 P1**

| 验证项 | 结果 | 脚本 |
|---|---|---|
| ① OpenAI 兼容端点 + tool calling | ✅ PASS | t1_model_toolcall.py |
| ② ReActAgent + 写工具 + ConfirmInterruptRail 中断/恢复 | ✅ PASS（approve + reject 双路径） | t2_hitl_interrupt.py |
| ③ run_agent_streaming 可桥接 SSE | ✅ PASS（token 流 + `__interaction__` 帧 + 流式恢复） | t3_streaming.py |
| 附加（§5.7 未验证项） | ✅ 全部有结论 | t4_extras.py |

## 关键实测事实（均为安装后源码/实跑一手结论）

### ① 模型接入（t1）
- `ModelClientConfig(client_provider="OpenAI", api_base, api_key, timeout, verify_ssl)` + `ModelRequestConfig(model=...)` → `Model.invoke(messages, tools=[...])` 正常返回 `AssistantMessage.tool_calls`（id/name/arguments 齐全）。
- Provider 枚举另含 `DeepSeek`/`Anthropic`/`SiliconFlow`/`DashScope` 等；`custom_headers` 支持多租户网关场景。
- `ModelClientConfig` 内置 `stream_first_chunk_timeout`(300s)/`stream_idle_timeout`(60s)/`max_retries`(1)/共享长连接客户端开关。

### ② HITL（t2）
- 组装：`Runner.resource_mgr.add_tool(t)` + `agent.ability_manager.add(t.card)` + `await agent.register_rail(ConfirmInterruptRail(tool_names=[...]))`。
- 中断：`Runner.run_agent(agent, {"query": ...}, session=<id>)` 返回 `{"result_type": "interrupt", "interrupt_ids": [...], "state": [OutputSchema(type="__interaction__", payload=InteractionOutput(id, ToolCallInterruptRequest(message, payload_schema, tool_name, tool_call_id, tool_args)))]}`。**中断时工具未执行（副作用日志为空，已断言）。**
- 恢复：`InteractiveInput().update(interrupt_id, {"approved": bool, "feedback": str, "auto_confirm": bool})` → `Runner.run_agent(agent, {"query": ii}, session=同 id)`。
- approve → 工具真实执行（副作用已断言），返回 `result_type="answer"`。
- reject(feedback) → 工具不执行，feedback 作为 ToolMessage 回传模型继续规划。**注意：模型可能按 feedback 重试同一工具 → 再次 interrupt（二次审批）**，实测 reject 后模型重试 1 次、再次拒绝后才结束。前端审批 UI/状态机需支持"同一轮多次审批"。
- `edit` 决策：`ApproveResult.new_args` 字段已在源码中确认（`interrupt_base.py`），`before_tool_call` 里 `ctx.inputs.tool_args` 可被改写 —— P1 自定义 `ApprovalEditRail` 可行，官方模式支持。
- `auto_confirm` 经 Session 状态持久化（`INTERRUPT_AUTO_CONFIRM_KEY`），对应 v2 的"本次会话不再询问"。

### ③ 流式（t3）
- `Runner.run_agent_streaming(agent, {"query": ...}, session=<id>)` 产出 `OutputSchema` 序列，实测帧类型：
  - `llm_reasoning`：reasoning token 增量（payload dict `{"content", "result_type"}`）
  - `llm_output`：**正文 token 增量**（实测 127 帧拼出完整回答）
  - `llm_usage`：token 用量；`tracer_agent`：链路追踪
  - `answer`：最终聚合帧（`payload={"output": ...}`，完成标记）
  - `__interaction__`：中断帧（payload.id 即 interrupt_id）
- 每帧可 1:1 映射 SSE event；sse_bridge 重写时按 `type` 分发即可。
- **interrupt 前后流式完整性**：中断前流正常终止于 `__interaction__` 帧；流式恢复（同 session + InteractiveInput）后 token 流与最终回答完整，工具在 approve 后真实执行。
- 注意：提前 break 消费流会触发 `current_session` ContextVar "created in a different Context" 警告（框架已知模式，完整消费无此问题；取消语义在 P1 需按 `agent.abort()` 处理）。

### 附加（t4，对应 §5.7）
- **最大迭代**：`ReActAgentConfig.max_iterations`（**默认 5**）实测生效——max_iterations=1 时工具执行完无剩余迭代生成答复，返回 `{"result_type": "error", "output": "Max iterations reached without completion"}`。⚠️ P1 必须显式调大（对标 v2 `AGENT_V2_RECURSION_LIMIT=50`）。
- **每轮工具调用上限**：无内置配置（源码无对应项）。已用自定义 `AgentRail.before_tool_call` 计数 + `ctx.extra["_skip_tool"]` + 注入 ToolMessage 实测拦截成功（2 次后跳过）。⚠️ 模型收到"超限"ToolMessage 后会重试（实测 rail 观测到 5 次意图），生产实现应在 skip 文案中明确"不要再调用"。
- **注解处理**：`from __future__ import annotations` 下 `@tool` schema 抽取正常（langchain 时代的 M1 坑在 agent-core 不存在）。
- **上下文裁剪**：`ContextEngineConfig`（`max_context_message_num`/`default_window_round_num`）+ `context_processors`（dialogue_compressor/message_offloader 等）存在，默认不启用；长会话策略 P1 按需配置。

### 附加（t5，P1 前置验证，2026-08-07 补）
- **会话全局状态**：工具内 `get_current_session()` 返回 `openjiuwen.core.session.agent.Session`，状态方法为 `get_state(key)/update_state(dict)`（非 get_global_state）；同 session id 跨 run 持久（in-memory），实测 run#2 读到 run#1 写入的 analysis_queue。
- **custom 流帧**：工具内 `await session.write_custom_stream({...})` 产出的帧以 CustomSchema 出现在 `run_agent_streaming` 输出中——**前提是调用方传 `stream_modes=[OUTPUT, CUSTOM]`**（默认不含 CUSTOM）。可替代 langgraph `get_stream_writer` 承载报告管线进度帧。
- 复现：`spikes/openjiuwen-p0/t5_session_state.py`。

## 环境/部署面发现

1. **cryptography 50.0.0 坑（新发现）**：2026-08 时 PyPI 上 cryptography 50.0.0 尚无 macOS x86_64 wheel，pip 默认选中后源码编译失败（需 Rust）。**spike 以 `pip install cryptography==46.0.7` 先行钉版解决**。离线 wheel 集（P4）制作时需将此钉版写入约束文件；ky10 需重新验证。
2. 依赖实测 80 项（transformers 5.14.1、pymilvus 2.6.9、trafilatura、fastmcp、dashscope 等全量安装成功，macOS x86_64 py3.12）。
3. `Runner.resource_mgr.add_tool` 重复注册同名工具会打 ERROR 日志（"resource already exist"）但不影响运行——进程级单例组装时需注意只注册一次。

## 对迁移方案的回写建议

- P1 可按原方案推进，补充三点：
  1. `max_iterations` 显式配置（≥50 或按场景调优），默认 5 对 11 工具编排偏小。
  2. 审批状态机支持"reject 后模型重试→再次审批"的循环；UI 需能区分"同一 tool_call 的二次审批"。
  3. SSE 帧映射表按实测类型实现：`llm_output`→正文增量、`llm_reasoning`→思考增量（可折叠）、`answer`→完成帧、`__interaction__`→审批请求、`llm_usage`→用量。
- P2（持久化）风险不变：本次 spike 全部走默认 in-memory checkpointer，SQLite/MySQL provider 仍需自研。
- P4 离线包：cryptography 钉版约束 + ky10/py3.12 重做 wheel 集。

## 复现

```bash
cd spikes/openjiuwen-p0
python3.12 -m venv .venv && .venv/bin/pip install --upgrade pip
.venv/bin/pip install cryptography==46.0.7 openjiuwen==0.1.16.post2
.venv/bin/python t1_model_toolcall.py   # ①
.venv/bin/python t2_hitl_interrupt.py   # ②
.venv/bin/python t3_streaming.py        # ③
.venv/bin/python t4_extras.py           # 附加
```
（t2/t3 会从 `backend/.env` 读取 LLM_API_KEY/LLM_BASE_URL/LLM_MODEL）

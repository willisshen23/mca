# agent_v3（openJiuwen agent-core）P1 对话运行时替换 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建 `backend/src/agent_v3/` 包，用 openJiuwen agent-core（ReActAgent + Rail）完整替换 agent_v2 的 langgraph/deepagents 对话运行时，SSE 帧契约与 HTTP 接口保持不变，经 `AGENT_V3_ENABLED` 开关灰度。

**Architecture:** agent_v3 与 agent_v2 并行共存、互不改写对方代码（唯一例外：v3 在自身启用时 monkeypatch `agent_v2.tools.report_gen.get_stream_writer`，与现有测试中的 patch 方式相同）。12 个业务工具的**函数体零改动复用**：v3 用 openjiuwen `@tool` 包一层壳，壳内经 `v2_tool.coroutine` 调用 v2 工具函数，用一个 duck-type 的假 `runtime`（`SimpleNamespace(state/context/tool_call_id)`）注入会话状态快照与请求上下文；v2 工具返回的 `Command(update=...)` 由适配层翻译为 agent-core 会话全局状态写入（`session.update_state`）。HITL 三决策（approve/edit/reject）由自定义 `ApprovalEditRail(BaseInterruptRail)` 实现；工具进度/状态透传由 `ToolProgressRail` 以 custom 流帧发出；每轮工具调用上限由 `ToolCallLimitRail` 实现。SSE 桥把 `OutputSchema/CustomSchema` 帧映射为与 v2 完全一致的 SSE 帧。持久化（SQLite/MySQL checkpointer）不在 P1 范围（P2），P1 会话状态为进程内 in-memory。

**Tech Stack:** Python 3.12、openjiuwen==0.1.16.post2（钉版）、cryptography==46.0.7（钉版，规避 PyPI 50.0.0 无 macOS x86_64 wheel 的源码编译坑）、FastAPI、pytest。

## Global Constraints

- `openjiuwen==0.1.16.post2` 精确钉版（0.x API 演进极快，沿用 deepagents 钉版策略）。
- `cryptography==46.0.7` 必须先于 openjiuwen 安装并写入 requirements（P0 实测坑）。
- agent_v2 代码**零改动**（import 层面的 patch 只允许从 agent_v3 侧发起，且仅在 `AGENT_V3_ENABLED=true` 时生效）。
- SSE 帧契约零变化：`node_update` / `approval_required` / `done` / `error` / `cancelled` 帧结构与 v2 完全一致（前端 `UiChatView.vue` 零改动）；done 帧 payload 字段：`request_id, final_response, html_report, analysis_queue, report_context, export_artifact, report_updated, awaiting_approval, tool_calls_count`；approval_required 帧 payload 字段：`tool, args, description, allowed_decisions, display_name, activities`。
- HTTP 契约零变化：复用 `/api/v2/agent/{run,resume,cancel,runs/{tid},runs/{tid}/stream}` 端点与请求体模型（`decision/tool/edited_args/message`），路由层按开关分流到 v3 runtime。
- `ReActAgentConfig.max_iterations` 必须显式设置为 50（默认 5 对 12 工具编排偏小；对标 v2 `agent_v2_recursion_limit=50`）。
- 每轮工具调用上限 8 次（对标 v2 `ToolCallLimitMiddleware(run_limit=8)`），超限 skip 文案必须明示"不要再调用该工具"（P0 实测：模型收到超限 ToolMessage 后会重试）。
- 审批状态机必须支持"reject 后模型按 feedback 重试同一工具 → 再次 interrupt → 二次审批"循环（P0 实测行为）。
- 请求级敏感参数（user_id/org_no/channel/file_path）只走 `agent_v2.state.request_context` 的 ContextVar（框架无关，直接复用），绝不进 LLM 对话。
- 审计契约不变：`record_turn_start(state_dict)` / `finish_turn(request_id, status, duration_ms, final_values, failure_reason)`，status ∈ `success/cancelled/awaiting_approval/failed`。
- 测试全部离线可跑（不依赖真实 LLM 端点）；实机联调单独一个 task 人工执行。
- 运行测试命令统一为 `cd backend && venv/bin/python -m pytest <path> -v`（backend/venv 是现有 langgraph 环境）。

## 已实测的 openjiuwen API 事实（本计划的代码依据，勿再臆测）

- 组装：`ReActAgent(card=AgentCard(id=..., description=...)).configure(ReActAgentConfig(model_config_obj=ModelRequestConfig(model=..., temperature=...), model_client_config=ModelClientConfig(client_provider="OpenAI", api_key=..., api_base=..., timeout=...), prompt_template=[{"role":"system","content":...}], max_iterations=50))`；工具注册 `Runner.resource_mgr.add_tool(t)` + `agent.ability_manager.add(t.card)`；Rail 注册 `await agent.register_rail(rail)`。
- 生命周期：`await Runner.start()` / `await Runner.stop()`。
- 驱动：`Runner.run_agent_streaming(agent, {"query": ...}, session=<AgentSession 实例>, stream_modes=[BaseStreamMode.OUTPUT, BaseStreamMode.CUSTOM])` 产出 `OutputSchema(type, index, payload)` / `CustomSchema`。
  - **必须传 `stream_modes` 含 `CUSTOM`，否则 custom 帧不出现（t5 实测）。**
- 会话实例：`from openjiuwen.core.session.agent import create_agent_session` → `create_agent_session(session_id=<thread_id>)` 返回 `openjiuwen.core.session.agent.Session`（别名 AgentSession），可跨多次 run 复用并直接传给 `session=` 参数（`Runner._prepare_agent` 源码确认支持 Session 实例）。
- 工具内拿会话：`from openjiuwen.core.session import get_current_session` → 返回 agent Session（`@with_session_for_class` 保证工具执行期内已注入，t5 实测）。**该类的状态方法是 `get_state(key)` / `update_state(dict)`（内部即全局状态），不是 `get_global_state`**；写自定义流帧 `await session.write_custom_stream({...})`（t5 实测帧以 `CustomSchema` 出现在流式输出，且全局状态跨同 session 的多次 run 持久）。
- 流帧类型（OutputSchema.type）：`llm_reasoning`（思考增量）、`llm_output`（正文 token 增量，payload dict 或二元 tuple，含 `content`）、`llm_usage`、`answer`（最终聚合，payload `{"output", "result_type"}`）、`__interaction__`（中断帧，payload 有 `.id` 即 interrupt_id，`.payload` 为 ToolCallInterruptRequest 含 `tool_name/tool_call_id/tool_args/message`）。**无工具开始/结束帧**——工具进度须由 Rail 自发 custom 帧。
- 中断恢复：`from openjiuwen.core.session import InteractiveInput` → `ii = InteractiveInput(); ii.update(interrupt_id, {...自定义 payload...})` → 再次 `run_agent_streaming(agent, {"query": ii}, session=同实例)`。Rail 内经 `ctx.extra[RESUME_USER_INPUT_KEY]`（基类 `_get_user_input` 已处理）拿到该 dict。
- `BaseInterruptRail`（`openjiuwen.harness.rails.interrupt.interrupt_base`）：子类实现 `resolve_interrupt(ctx, tool_call, user_input, auto_confirm_config)` 返回 `self.approve(new_args=None) / self.reject(tool_result=...) / self.interrupt(InterruptRequest(message=..., payload_schema=...))`；approve 的 `new_args` 为 **JSON 字符串**（`ctx.inputs.tool_args = new_args` → `tool_call.arguments`，ToolCall.arguments 即 JSON 字符串约定）。
- `AgentRail`（`openjiuwen.core.single_agent.rail.base`）可用 hook：`before_invoke(ctx)`（`ctx.inputs.query`）、`before_tool_call(ctx)`（`ctx.inputs.tool_name/tool_args/tool_call`，`ctx.session`，`ctx.extra`）、`after_tool_call(ctx)`（`ctx.inputs.tool_result` 已填充）。拦截工具执行：`ctx.extra["_skip_tool"] = True; ctx.inputs.tool_result = "..."; ctx.inputs.tool_msg = ToolMessage(content=..., tool_call_id=...)`（t4 实测，ToolMessage 来自 `openjiuwen.core.foundation.llm`）。
- `langgraph.config.get_stream_writer()` 在 langgraph 运行上下文之外**抛 RuntimeError**（实测）→ v3 必须 patch `src.agent_v2.tools.report_gen.get_stream_writer`。
- `Runner.resource_mgr.add_tool` 同名重复注册只打 ERROR 日志不抛异常，但单例组装仍须保证只注册一次。
- 取消：P0 发现提前中断消费流有 ContextVar 告警；v3 取消语义 = 停止消费流（async generator aclose）+ 取消驱动 task，粒度与 v2"流事件间隙生效"一致。

## 已知取舍（P1 接受、写进验收文档）

1. **会话重载降级**：`conversations.py` 历史重载直接读 langgraph checkpoint（`channel_values["messages"]` 等），v3 无 checkpoint → v3 开关下刷新页面后历史消息/报告卡片不恢复（进程内会话状态仍在，可继续对话）。P2 持久化阶段修复。
2. **分层模型路由（TieredModelMiddleware）不迁移**：v3 固定用主模型（`agent_v2_main_llm_*`，缺省回退全局 `llm_*`）。cheap/fallback  tier 是成本优化非正确性功能，P1 后单独立项。
3. 报告管线（report_pipeline 9 节点）已是纯函数编排（`run_report_pipeline`，无 langgraph 图实例），P1 原样复用；P3 再议迁 Workflow。

---

### Task 1: 依赖钉版、配置项、t5 结论回写

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/src/config.py`（在 `agent_v2_recursion_limit` 定义附近追加，约 :104-108 处）
- Modify: `docs/superpowers/specs/2026-08-07-openjiuwen-p0-spike-report.md`（追加 t5 小节）
- Test: `backend/tests/agent_v3/__init__.py`（空文件）、`backend/tests/agent_v3/test_v3_config.py`

**Interfaces:**
- Produces（后续所有 task 依赖）:
  - `get_settings().agent_v3_enabled: bool`（默认 `False`，env `AGENT_V3_ENABLED`）
  - `get_settings().agent_v3_max_iterations: int`（默认 `50`，env `AGENT_V3_MAX_ITERATIONS`）

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/agent_v3/__init__.py`（空）与 `backend/tests/agent_v3/test_v3_config.py`：

```python
"""agent_v3 配置项测试。"""

from src.config import Settings


def test_agent_v3_defaults():
    s = Settings(_env_file=None)
    assert s.agent_v3_enabled is False
    assert s.agent_v3_max_iterations == 50


def test_agent_v3_env_override(monkeypatch):
    monkeypatch.setenv("AGENT_V3_ENABLED", "true")
    monkeypatch.setenv("AGENT_V3_MAX_ITERATIONS", "30")
    s = Settings(_env_file=None)
    assert s.agent_v3_enabled is True
    assert s.agent_v3_max_iterations == 30
```

（参照 `backend/tests/agent_v2/test_runtime_config.py` 中 Settings 的构造方式；若该文件用了不同的构造习惯，以其为准调整。）

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_config.py -v`
Expected: FAIL（`Settings` 无 `agent_v3_enabled` 属性）

- [ ] **Step 3: 加配置项**

在 `backend/src/config.py` 的 `agent_v2_recursion_limit` 字段定义之后追加（照抄现有字段的 pydantic Field 风格，env alias 参照同文件 `AGENT_V2_RECURSION_LIMIT` 的写法）：

```python
    agent_v3_enabled: bool = Field(default=False, alias="AGENT_V3_ENABLED")
    agent_v3_max_iterations: int = Field(default=50, ge=1, alias="AGENT_V3_MAX_ITERATIONS")
```

注意：若现有字段用的是 `validation_alias` 或 `AliasChoices`，严格照抄同文件相邻字段的写法，不要发明新风格。若 Settings 配置了 `populate_by_name`，保持与相邻字段一致即可。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_config.py -v`
Expected: PASS 2 例

- [ ] **Step 5: 依赖钉版**

在 `backend/requirements.txt` 的 deepagents 钉版注释块之后追加：

```
# agent_v3 (openJiuwen agent-core) — 精确钉版，0.x API 仍在演进
# cryptography 必须钉 46.0.7：PyPI 50.0.0 无 macOS x86_64 wheel 会触发源码编译（需 Rust）
cryptography==46.0.7
openjiuwen==0.1.16.post2
```

然后在 backend venv 安装并验证：

```bash
cd backend && venv/bin/pip install cryptography==46.0.7 openjiuwen==0.1.16.post2
venv/bin/python -c "from openjiuwen.core.single_agent import ReActAgent; from openjiuwen.core.runner import Runner; print('openjiuwen import ok')"
```

Expected: 打印 `openjiuwen import ok`。若 pip 解析与现有依赖冲突（如 openai/pydantic 版本区间），记录冲突项并停下报告，不要擅自放宽其他依赖钉版。

- [ ] **Step 6: t5 结论回写 spike 报告**

在 `docs/superpowers/specs/2026-08-07-openjiuwen-p0-spike-report.md` 的「附加（t4）」小节后追加：

```markdown
### 附加（t5，P1 前置验证，2026-08-07 补）
- **会话全局状态**：工具内 `get_current_session()` 返回 `openjiuwen.core.session.agent.Session`，状态方法为 `get_state(key)/update_state(dict)`（非 get_global_state）；同 session id 跨 run 持久（in-memory），实测 run#2 读到 run#1 写入的 analysis_queue。
- **custom 流帧**：工具内 `await session.write_custom_stream({...})` 产出的帧以 CustomSchema 出现在 `run_agent_streaming` 输出中——**前提是调用方传 `stream_modes=[OUTPUT, CUSTOM]`**（默认不含 CUSTOM）。可替代 langgraph `get_stream_writer` 承载报告管线进度帧。
- 复现：`spikes/openjiuwen-p0/t5_session_state.py`。
```

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/src/config.py backend/tests/agent_v3/ spikes/openjiuwen-p0/t5_session_state.py docs/superpowers/specs/2026-08-07-openjiuwen-p0-spike-report.md
git commit -m "feat(agent_v3): P1 依赖钉版与 AGENT_V3_ENABLED/MAX_ITERATIONS 配置"
```

---

### Task 2: 会话注册表 `agent_v3/sessions.py`

**Files:**
- Create: `backend/src/agent_v3/__init__.py`
- Create: `backend/src/agent_v3/sessions.py`
- Test: `backend/tests/agent_v3/test_v3_sessions.py`

**Interfaces:**
- Consumes: `create_agent_session`（openjiuwen，见"已实测事实"）。
- Produces（Task 6/8/9 依赖）:
  - `get_or_create_session(thread_id: str) -> Session`（同步；首次创建 `create_agent_session(session_id=thread_id)` 并登记，之后返回同一实例）
  - `set_pending_interrupt(thread_id: str, interrupt_id: str) -> None`
  - `get_pending_interrupt(thread_id: str) -> str | None`
  - `clear_pending_interrupt(thread_id: str) -> None`
  - `read_business_state(thread_id: str) -> dict` — 从会话全局状态读 `{"html_report", "analysis_queue", "report_context", "activity_list", "formatted_output_path"}` 五键，缺失给 `""`/`[]`/`{}` 默认；无会话时全默认
  - `reset_sessions() -> None`（测试与 shutdown 用）

- [ ] **Step 1: 写失败测试**

```python
"""agent_v3 会话注册表测试（不触真实 openjiuwen，monkeypatch create_agent_session）。"""

from src.agent_v3 import sessions


class _FakeState:
    def __init__(self):
        self._data = {}

    def get_global(self, key):
        return self._data.get(key)

    def update_global(self, data):
        self._data.update(data)


class _FakeSession:
    """模拟 openjiuwen.core.session.agent.Session 的 get_state/update_state。"""

    def __init__(self, session_id):
        self.session_id = session_id
        self._state = _FakeState()

    def get_state(self, key=None):
        return self._state.get_global(key)

    def update_state(self, data):
        self._state.update_global(data)


def setup_function():
    sessions.reset_sessions()


def test_get_or_create_returns_same_instance(monkeypatch):
    monkeypatch.setattr(sessions, "create_agent_session", lambda session_id=None: _FakeSession(session_id))
    a = sessions.get_or_create_session("t1")
    b = sessions.get_or_create_session("t1")
    assert a is b
    c = sessions.get_or_create_session("t2")
    assert c is not a


def test_pending_interrupt_cycle(monkeypatch):
    monkeypatch.setattr(sessions, "create_agent_session", lambda session_id=None: _FakeSession(session_id))
    assert sessions.get_pending_interrupt("t1") is None
    sessions.set_pending_interrupt("t1", "int-1")
    assert sessions.get_pending_interrupt("t1") == "int-1"
    sessions.clear_pending_interrupt("t1")
    assert sessions.get_pending_interrupt("t1") is None


def test_read_business_state_defaults_without_session():
    state = sessions.read_business_state("nonexistent")
    assert state == {
        "html_report": "",
        "analysis_queue": [],
        "report_context": {},
        "activity_list": [],
        "formatted_output_path": "",
    }


def test_read_business_state_reads_written_keys(monkeypatch):
    monkeypatch.setattr(sessions, "create_agent_session", lambda session_id=None: _FakeSession(session_id))
    s = sessions.get_or_create_session("t1")
    s.update_state({"html_report": "<html>x</html>", "analysis_queue": [{"activity_id": "A1"}]})
    state = sessions.read_business_state("t1")
    assert state["html_report"] == "<html>x</html>"
    assert state["analysis_queue"] == [{"activity_id": "A1"}]
    assert state["report_context"] == {}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_sessions.py -v`
Expected: FAIL（`No module named 'src.agent_v3'`）

- [ ] **Step 3: 实现**

`backend/src/agent_v3/__init__.py`：

```python
"""agent_v3：openJiuwen agent-core 对话运行时（与 agent_v2 并行，AGENT_V3_ENABLED 开关）。

openjiuwen 导入隔离：全仓库仅 agent_v3 包内允许 import openjiuwen。
"""
```

`backend/src/agent_v3/sessions.py`：

```python
"""thread_id → agent-core Session 注册表与待决中断登记。

P1 为进程内 in-memory（P2 才接持久化 checkpointer）：
进程重启后会话状态丢失，与 P1 验收文档的已知取舍一致。
"""
from __future__ import annotations

import threading

from openjiuwen.core.session.agent import create_agent_session

_sessions: dict[str, object] = {}
_pending_interrupts: dict[str, str] = {}
_lock = threading.Lock()

#: done 帧需要从会话状态读取的业务键及其默认值
_BUSINESS_STATE_DEFAULTS = {
    "html_report": "",
    "analysis_queue": [],
    "report_context": {},
    "activity_list": [],
    "formatted_output_path": "",
}


def get_or_create_session(thread_id: str):
    with _lock:
        session = _sessions.get(thread_id)
        if session is None:
            session = create_agent_session(session_id=thread_id)
            _sessions[thread_id] = session
        return session


def set_pending_interrupt(thread_id: str, interrupt_id: str) -> None:
    with _lock:
        _pending_interrupts[thread_id] = interrupt_id


def get_pending_interrupt(thread_id: str) -> str | None:
    with _lock:
        return _pending_interrupts.get(thread_id)


def clear_pending_interrupt(thread_id: str) -> None:
    with _lock:
        _pending_interrupts.pop(thread_id, None)


def read_business_state(thread_id: str) -> dict:
    with _lock:
        session = _sessions.get(thread_id)
    state = {key: (list(value) if isinstance(value, list) else dict(value) if isinstance(value, dict) else value)
             for key, value in _BUSINESS_STATE_DEFAULTS.items()}
    if session is None:
        return state
    for key, default in _BUSINESS_STATE_DEFAULTS.items():
        value = session.get_state(key)
        state[key] = value if value is not None else default
    return state


def reset_sessions() -> None:
    with _lock:
        _sessions.clear()
        _pending_interrupts.clear()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_sessions.py -v`
Expected: PASS 4 例

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_v3/ backend/tests/agent_v3/
git commit -m "feat(agent_v3): 会话注册表与待决中断登记"
```

---

### Task 3: 工具适配层 `agent_v3/tools/__init__.py`（适配核心 + 首个工具）

**Files:**
- Create: `backend/src/agent_v3/tools/__init__.py`
- Test: `backend/tests/agent_v3/test_v3_tool_adapter.py`

**Interfaces:**
- Consumes: `src.agent_v2.state.request_context.get_request_context`（框架无关，直接复用）；v2 工具对象（langchain StructuredTool，其 `.coroutine` 是底层 async 函数）；langgraph `Command`（`result.update` dict）；`get_current_session`（openjiuwen）。
- Produces（Task 4 依赖）:
  - `async def invoke_v2_tool(v2_tool, args: dict) -> str` — 用假 runtime 调 v2 工具 coroutine；若返回 Command：把 `update` 中除 `messages` 外的键写入当前会话状态，返回 ToolMessage 的 content；若返回 str 原样返回。
  - 假 runtime 规格：`SimpleNamespace(state=<会话业务状态快照 dict>, context=<request_context ContextVar dict>, tool_call_id="")`——与 `_common.resolve_state`（要 dict）/`resolve_context`（兼容 dict）的读取契约匹配。

设计要点（实现者须知）：
- `state` 快照键集 = v2 工具实际会读的键全集：`analysis_queue, activity_list, report_context, html_report, uploaded_activity_dataset, data_summary, formatted_output_path, request_id, original_user_text`。从 `get_current_session().get_state(key)` 逐键读取组装；`request_id/original_user_text` 从 request_context ContextVar 补（它们是 turn 级数据，v3 不落会话状态）。
- v2 工具内 `runtime.tool_call_id` 只用于构造 ToolMessage（Command 内），适配层翻译时丢弃该 ToolMessage 只取 content，因此假 runtime 给 `tool_call_id=""` 无害。
- `get_current_session()` 在 openjiuwen 工具执行期内必然可用（t5 实测）；防御性处理：拿不到会话时 state 快照给全空 dict、Command 的状态更新静默丢弃并打 WARNING（保证只读工具不受影响）。

- [ ] **Step 1: 写失败测试**

```python
"""agent_v3 工具适配层测试：假 v2 工具 + 假会话，不触 langgraph 运行时与 LLM。"""

from types import SimpleNamespace

import pytest
from langgraph.types import Command
from langchain_core.messages import ToolMessage

from src.agent_v3 import tools as v3_tools
from src.agent_v2.state.request_context import set_request_context, reset_request_context


class _FakeSession:
    def __init__(self):
        self._data = {}

    def get_state(self, key=None):
        return self._data.get(key)

    def update_state(self, data):
        self._data.update(data)


class _FakeV2Tool:
    """模拟 langchain StructuredTool：.coroutine 是底层 async 函数。"""

    def __init__(self, func):
        self.coroutine = func
        self.name = func.__name__


@pytest.fixture
def fake_session(monkeypatch):
    session = _FakeSession()
    monkeypatch.setattr(v3_tools, "get_current_session", lambda: session)
    return session


async def test_plain_string_result_passthrough(fake_session):
    async def my_tool(keyword: str = "", runtime=None):
        return f"查到 {keyword}"

    result = await v3_tools.invoke_v2_tool(_FakeV2Tool(my_tool), {"keyword": "贷款"})
    assert result == "查到 贷款"


async def test_command_update_written_to_session(fake_session):
    async def my_tool(runtime=None):
        state = runtime.state  # 适配层给的快照
        queue = list(state.get("analysis_queue") or []) + [{"activity_id": "A1"}]
        return Command(update={
            "messages": [ToolMessage(content='{"status":"ok"}', tool_call_id=runtime.tool_call_id)],
            "analysis_queue": queue,
        })

    result = await v3_tools.invoke_v2_tool(_FakeV2Tool(my_tool), {})
    assert result == '{"status":"ok"}'
    assert fake_session.get_state("analysis_queue") == [{"activity_id": "A1"}]


async def test_state_snapshot_reads_session(fake_session):
    fake_session.update_state({"activity_list": [{"activity_id": "A9"}]})
    seen = {}

    async def my_tool(runtime=None):
        seen["activity_list"] = runtime.state.get("activity_list")
        return "ok"

    await v3_tools.invoke_v2_tool(_FakeV2Tool(my_tool), {})
    assert seen["activity_list"] == [{"activity_id": "A9"}]


async def test_context_from_request_contextvar(fake_session):
    seen = {}
    token = set_request_context({"user_id": "U1", "org_no": "3201"})

    async def my_tool(runtime=None):
        seen["ctx"] = runtime.context
        return "ok"

    try:
        await v3_tools.invoke_v2_tool(_FakeV2Tool(my_tool), {})
    finally:
        reset_request_context(token)
    assert seen["ctx"]["user_id"] == "U1"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_tool_adapter.py -v`
Expected: FAIL（`No module named 'src.agent_v3.tools'`）

- [ ] **Step 3: 实现**

`backend/src/agent_v3/tools/__init__.py`：

```python
"""agent_v3 工具层：openjiuwen @tool 壳 + v2 工具函数体复用适配器。

复用原理：v2 工具（langchain StructuredTool）的 .coroutine 是底层 async 函数，
签名末尾带 `runtime: ToolRuntime = None`。本层构造 duck-type 假 runtime
（state=dict 快照 / context=dict / tool_call_id=""）注入，v2 函数体零改动；
返回的 Command(update=...) 翻译为 agent-core 会话全局状态写入。
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from langgraph.types import Command
from openjiuwen.core.foundation.tool import tool
from openjiuwen.core.session import get_current_session

from src.agent_v2.state.request_context import get_request_context
from src.agent_v2.tools import activity_query as v2_activity_query

logger = logging.getLogger("activity-analysis.agent")

#: v2 工具经 resolve_state(runtime) 可能读取的 state 键全集（会话状态部分）
_SESSION_STATE_KEYS = (
    "analysis_queue",
    "activity_list",
    "report_context",
    "html_report",
    "uploaded_activity_dataset",
    "data_summary",
    "formatted_output_path",
)

#: turn 级键：v2 存图状态，v3 由 request_context ContextVar 提供
_TURN_STATE_KEYS = ("request_id", "original_user_text")


def _state_snapshot(session) -> dict:
    snapshot: dict[str, Any] = {}
    for key in _SESSION_STATE_KEYS:
        value = session.get_state(key)
        if value is not None:
            snapshot[key] = value
    ctx = get_request_context()
    for key in _TURN_STATE_KEYS:
        if ctx.get(key):
            snapshot[key] = ctx[key]
    return snapshot


async def invoke_v2_tool(v2_tool, args: dict) -> str:
    """用假 runtime 调用 v2 工具 coroutine，把 Command 翻译为会话状态写入。"""
    try:
        session = get_current_session()
    except Exception:
        session = None
    state = _state_snapshot(session) if session is not None else {}
    runtime = SimpleNamespace(state=state, context=get_request_context(), tool_call_id="")
    result = await v2_tool.coroutine(**args, runtime=runtime)
    if isinstance(result, Command):
        update = result.update or {}
        messages = update.get("messages") or []
        content = getattr(messages[0], "content", "") if messages else ""
        state_updates = {k: v for k, v in update.items() if k != "messages"}
        if state_updates:
            if session is not None:
                session.update_state(state_updates)
            else:
                logger.warning("agent_v3 工具 %s 的状态更新被丢弃（无会话）: keys=%s",
                               getattr(v2_tool, "name", "?"), list(state_updates))
        return content
    return result


@tool
async def search_activities(keyword: str = "", activity_type: str = "", channel: str = "",
                            start_date: str = "", end_date: str = "", limit: int = 20) -> str:
    """按关键词/渠道/日期等条件查询银行营销活动，返回活动列表。参数：keyword 搜索关键词（活动名称/编号模糊匹配）；activity_type 活动类型；channel 渠道；start_date 开始日期（YYYY-MM-DD）；end_date 结束日期（YYYY-MM-DD）；limit 返回条数上限。"""
    return await invoke_v2_tool(v2_activity_query.search_activities, {
        "keyword": keyword, "activity_type": activity_type, "channel": channel,
        "start_date": start_date, "end_date": end_date, "limit": limit,
    })
```

注意（docstring 规则，2026-08-07 评审后修正）：openjiuwen `@tool` 的工具 description **在 docstring 首个空行处截断**，且参数级 description 不从中文"参数："段解析（实测，见 Task 3 评审）。因此 v3 壳的 docstring 必须写成**无空行的单段**：把 v2 工具 docstring 全文（含使用指引）与参数语义连成一段。search_activities 范例（以 `agent_v2/tools/activity_query.py` 的 docstring 与 args_schema Field description 原文为准拼接，不改写措辞）：

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_tool_adapter.py -v`
Expected: PASS 4 例

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_v3/tools/ backend/tests/agent_v3/test_v3_tool_adapter.py
git commit -m "feat(agent_v3): 工具适配层 invoke_v2_tool + search_activities 壳"
```

---

### Task 4: 全部 12 工具壳 + write_todos

**Files:**
- Modify: `backend/src/agent_v3/tools/__init__.py`
- Test: `backend/tests/agent_v3/test_v3_tool_schemas.py`

**Interfaces:**
- Consumes: Task 3 的 `invoke_v2_tool`；v2 各工具模块（`src.agent_v2.tools.*`）的工具对象与 args_schema。
- Produces（Task 7 依赖）:
  - `ALL_V3_TOOLS: list` — 12 个 openjiuwen 工具对象 + `write_todos`，顺序与 v2 `ALL_TOOLS` 一致、write_todos 排最后
  - 13 个工具名与 v2 完全一致：`search_activities, get_activity_detail, get_available_templates, get_available_skills, parse_uploaded_data, add_to_analysis_queue, remove_from_analysis_queue, update_analysis_config, get_report_content, generate_report, modify_report, export_report, write_todos`

- [ ] **Step 1: 写失败测试（schema 等价性——本 task 的核心防漂移断言）**

`backend/tests/agent_v3/test_v3_tool_schemas.py`：

```python
"""v3 工具壳的 schema 与 v2 args_schema 字段集等价（防誊写漂移）。"""

from src.agent_v3 import tools as v3_tools
from src.agent_v2.tools import (
    activity_query, analysis_queue, data_parse, report_export,
    report_modify, report_gen, skill, template,
)

# (v3 工具名, v2 工具对象) —— 12 个业务工具全清单
_TOOL_PAIRS = [
    ("search_activities", activity_query.search_activities),
    ("get_activity_detail", activity_query.get_activity_detail),
    ("get_available_templates", template.get_available_templates),
    ("get_available_skills", skill.get_available_skills),
    ("parse_uploaded_data", data_parse.parse_uploaded_data),
    ("add_to_analysis_queue", analysis_queue.add_to_analysis_queue),
    ("remove_from_analysis_queue", analysis_queue.remove_from_analysis_queue),
    ("update_analysis_config", analysis_queue.update_analysis_config),
    ("get_report_content", report_modify.get_report_content),
    ("generate_report", report_gen.generate_report),
    ("modify_report", report_modify.modify_report),
    ("export_report", report_export.export_report),
]


def _v3_tool_by_name(name):
    for t in v3_tools.ALL_V3_TOOLS:
        if t.card.name == name:
            return t
    raise AssertionError(f"v3 缺少工具 {name}")


def test_all_v2_tools_have_v3_shell():
    v3_names = {t.card.name for t in v3_tools.ALL_V3_TOOLS}
    for name, _ in _TOOL_PAIRS:
        assert name in v3_names
    assert "write_todos" in v3_names


def test_schema_fields_match_v2():
    for name, v2_tool in _TOOL_PAIRS:
        v3_props = set(_v3_tool_by_name(name).card.input_params.get("properties", {}))
        v2_props = set(v2_tool.args_schema.model_fields) - {"runtime"}
        assert v3_props == v2_props, f"{name}: v3={v3_props} v2={v2_props}"


def test_card_description_not_truncated():
    """openjiuwen 在 docstring 首个空行截断 description——断言 v2 使用指引的关键词
    完整出现在 v3 card.description 中（每个工具取 v2 docstring 末尾语义的标志短语）。"""
    sentinels = {
        # 每个工具取 v2 docstring 中后段的标志短语（实现时先读 v2 docstring 原句再填）
        "add_to_analysis_queue": "generate_report",
        "generate_report": "再次调用",
    }
    for name, phrase in sentinels.items():
        desc = _v3_tool_by_name(name).card.description
        assert phrase in desc, f"{name} 的 description 被截断（缺 {phrase!r}）: {desc!r}"
```

注意：v2 langchain 工具对象的 args_schema 属性名以实际为准（langchain StructuredTool 是 `.args_schema`；`model_fields` 是 pydantic v2 API）。若 v2 工具对象没有 `.args_schema`（个别工具可能没用 args_schema= 声明），改为读 `.args` 或在测试里硬编码该工具的期望字段集——以实际读到的为准调整，并在计划偏离处留注释。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_tool_schemas.py -v`
Expected: FAIL（`ALL_V3_TOOLS` 不存在）

- [ ] **Step 3: 实现全部壳**

在 `backend/src/agent_v3/tools/__init__.py` 中，按 Task 3 search_activities 的同一模式补齐其余 11 个业务工具壳。**每个壳必须**：① 函数名/参数名/类型/默认值与 v2 args_schema 一致（去掉 `runtime`）；② docstring 为**无空行的单段**（openjiuwen 在首个空行截断 description，实测）：v2 工具 docstring 全文（使用指引不得丢）+ 参数语义连成一段，措辞以 v2 原文为准；③ 函数体一行 `return await invoke_v2_tool(<v2 模块>.<工具名>, {...})`。

逐工具的参数清单（实现前逐个打开 v2 源文件核对 args_schema，下表仅供对照——以源码为准）：

| 工具 | 参数（除 runtime） |
|---|---|
| search_activities | keyword="", activity_type="", channel="", start_date="", end_date="", limit=20 |
| get_activity_detail | activity_id: str |
| get_available_templates | template_type="", keyword="" |
| get_available_skills | category="", keyword="" |
| parse_uploaded_data | confirm: bool = True |
| add_to_analysis_queue | activity_ids: list[str], perspective="", metrics=None, dimensions=None |
| remove_from_analysis_queue | activity_ids: list[str] |
| update_analysis_config | activity_id: str, perspective="", metrics=None, dimensions=None |
| get_report_content | summary_length: int = 2000 |
| generate_report | activity_ids=None, data_source="analysis_queue", metrics=None, dimensions=None, perspective=None, chart_style=None, report_theme=None, analysis_focus="", confirm_mixed=False |
| modify_report | content_changes=None, chart_replacements=None, style_changes=None, free_instruction="" |
| export_report | format="html", output_filename="" |

注意：list 参数的可空性与默认值严格照抄 v2 args_schema（如 `metrics: list[str] | None = None`）；`from __future__ import annotations` 下 openjiuwen @tool 抽取正常（t4 实测），但**不要用 `Optional[...]` 之外的非标写法**。

另加 write_todos（v2 暴露的 deepagents 内置规划工具的 v3 等价物，存会话状态）：

```python
@tool
async def write_todos(todos: list[str]) -> str:
    """将当前任务的待办清单写入会话（规划辅助）。参数：todos 待办事项文本列表。"""
    session = get_current_session()
    session.update_state({"todos": list(todos)})
    return f"已记录 {len(todos)} 条待办"
```

文件末尾：

```python
ALL_V3_TOOLS = [
    search_activities,
    get_activity_detail,
    get_available_templates,
    get_available_skills,
    parse_uploaded_data,
    add_to_analysis_queue,
    remove_from_analysis_queue,
    update_analysis_config,
    get_report_content,
    generate_report,
    modify_report,
    export_report,
    write_todos,
]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_tool_schemas.py tests/agent_v3/test_v3_tool_adapter.py -v`
Expected: PASS（schema 等价 2 例 + 适配层 4 例）

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_v3/tools/ backend/tests/agent_v3/test_v3_tool_schemas.py
git commit -m "feat(agent_v3): 12 业务工具壳 + write_todos，schema 与 v2 等价"
```

---

### Task 5: 审批三决策 Rail `agent_v3/rails.py`（ApprovalEditRail）

**Files:**
- Create: `backend/src/agent_v3/rails.py`
- Test: `backend/tests/agent_v3/test_v3_approval_rail.py`

**Interfaces:**
- Consumes: openjiuwen `BaseInterruptRail` / `InterruptRequest` / `AgentCallbackContext` / `ToolCall`（见"已实测事实"）。
- Produces（Task 7/9 依赖）:
  - `class ApprovalEditRail(BaseInterruptRail)` — `__init__(self, tool_names)`；resume payload 契约为 `{"decision": "approve"|"edit"|"reject", "edited_args": dict, "message": str}`（由 Task 9 runtime 从 HTTP resume 请求构造后经 `InteractiveInput.update` 传入）。
  - 决策映射：approve → `self.approve()`；edit → `self.approve(new_args=json.dumps(edited_args, ensure_ascii=False))`；reject → `self.reject(tool_result=<feedback 文本>)`；user_input 为 None 或无法解析 → `self.interrupt(InterruptRequest(message=<确认文案>, payload_schema=<schema>))`。
  - reject 的 tool_result 文本必须含"不要再调用该工具"指引（P0 实测模型会按 feedback 重试）。

- [ ] **Step 1: 写失败测试**

```python
"""ApprovalEditRail 三决策单元测试（直接调 resolve_interrupt，不起 agent）。"""

import json
from types import SimpleNamespace

import pytest

from openjiuwen.core.foundation.llm.schema.tool_call import ToolCall
from openjiuwen.harness.rails.interrupt.interrupt_base import (
    ApproveResult, InterruptResult, RejectResult,
)

from src.agent_v3.rails import ApprovalEditRail


def _ctx():
    return SimpleNamespace(extra={}, session=None)


def _tool_call():
    return ToolCall(id="call-1", type="function", name="modify_report",
                    arguments='{"free_instruction":"改标题"}', index=0)


async def test_first_call_interrupts():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    decision = await rail.resolve_interrupt(_ctx(), _tool_call(), None, None)
    assert isinstance(decision, InterruptResult)
    schema = decision.request.payload_schema
    assert "decision" in schema.get("properties", {})


async def test_approve():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    decision = await rail.resolve_interrupt(
        _ctx(), _tool_call(), {"decision": "approve"}, None)
    assert isinstance(decision, ApproveResult)
    assert decision.new_args is None


async def test_edit_rewrites_args_as_json_string():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    edited = {"free_instruction": "改成中文标题"}
    decision = await rail.resolve_interrupt(
        _ctx(), _tool_call(), {"decision": "edit", "edited_args": edited}, None)
    assert isinstance(decision, ApproveResult)
    assert json.loads(decision.new_args) == edited
    assert isinstance(decision.new_args, str)


async def test_reject_carries_feedback_and_no_retry_guidance():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    decision = await rail.resolve_interrupt(
        _ctx(), _tool_call(), {"decision": "reject", "message": "先别改"}, None)
    assert isinstance(decision, RejectResult)
    assert "先别改" in str(decision.tool_result)
    assert "不要再调用" in str(decision.tool_result)


async def test_unparseable_input_reinterrupts():
    rail = ApprovalEditRail(tool_names=["modify_report"])
    decision = await rail.resolve_interrupt(_ctx(), _tool_call(), {"foo": 1}, None)
    assert isinstance(decision, InterruptResult)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_approval_rail.py -v`
Expected: FAIL（`No module named 'src.agent_v3.rails'`）

- [ ] **Step 3: 实现**

`backend/src/agent_v3/rails.py`（本 task 只含 ApprovalEditRail；Task 6 往同文件追加）：

```python
"""agent_v3 自定义 Rail：审批三决策 / 工具调用上限 / 工具进度流帧。"""
from __future__ import annotations

import json
import logging
from typing import Iterable, Optional

from openjiuwen.core.single_agent.interrupt.response import InterruptRequest
from openjiuwen.core.single_agent.rail.base import AgentCallbackContext
from openjiuwen.core.foundation.llm.schema.tool_call import ToolCall
from openjiuwen.harness.rails.interrupt.interrupt_base import (
    BaseInterruptRail, InterruptDecision,
)

logger = logging.getLogger("activity-analysis.agent")

#: resume payload 的 JSON Schema（随中断帧透传给前端/调用方，自描述用）
APPROVAL_PAYLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["approve", "edit", "reject"]},
        "edited_args": {"type": "object"},
        "message": {"type": "string"},
    },
    "required": ["decision"],
}


class ApprovalEditRail(BaseInterruptRail):
    """写工具审批：approve / edit（改写参数）/ reject（feedback 回传模型）。

    对标 v2 interrupt_on 的 allowed_decisions=["approve", "edit", "reject"]。
    """

    def __init__(self, tool_names: Optional[Iterable[str]] = None,
                 message: str = "请确认是否执行该操作"):
        super().__init__(tool_names=tool_names)
        self._message = message

    async def resolve_interrupt(
            self,
            ctx: AgentCallbackContext,
            tool_call: Optional[ToolCall],
            user_input,
            auto_confirm_config: Optional[dict] = None,
    ) -> InterruptDecision:
        if not isinstance(user_input, dict):
            return self.interrupt(InterruptRequest(
                message=self._message,
                payload_schema=APPROVAL_PAYLOAD_SCHEMA,
            ))
        decision = user_input.get("decision")
        if decision == "approve":
            return self.approve()
        if decision == "edit":
            edited_args = user_input.get("edited_args") or {}
            return self.approve(new_args=json.dumps(edited_args, ensure_ascii=False))
        if decision == "reject":
            feedback = (user_input.get("message") or "用户拒绝了该操作").strip()
            return self.reject(tool_result=(
                f"用户拒绝了本次操作。用户反馈：{feedback}。"
                "请尊重用户决定，不要再调用该工具，直接用文字回复用户。"
            ))
        return self.interrupt(InterruptRequest(
            message=self._message,
            payload_schema=APPROVAL_PAYLOAD_SCHEMA,
        ))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_approval_rail.py -v`
Expected: PASS 5 例

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_v3/rails.py backend/tests/agent_v3/test_v3_approval_rail.py
git commit -m "feat(agent_v3): ApprovalEditRail 审批三决策（approve/edit/reject）"
```

---

### Task 6: 工具上限 Rail + 工具进度 Rail

**Files:**
- Modify: `backend/src/agent_v3/rails.py`
- Test: `backend/tests/agent_v3/test_v3_rails.py`

**Interfaces:**
- Consumes: `AgentRail` hook 契约（before_invoke / before_tool_call / after_tool_call，`ctx.inputs` / `ctx.session` / `ctx.extra`）；`ToolMessage`（openjiuwen）。
- Produces（Task 7/8 依赖）:
  - `class ToolCallLimitRail(AgentRail)` — `__init__(self, max_calls: int = 8)`；`before_invoke` 重置计数；`before_tool_call` 计数，超过 max_calls 时设 `ctx.extra["_skip_tool"]=True` + `ctx.inputs.tool_result` + `ctx.inputs.tool_msg`，文案含"不要再调用"。
  - `class ToolProgressRail(AgentRail)` — `__init__(self, suppressed_tools: frozenset = frozenset({"generate_report"}), safe_state_keys: tuple = ("analysis_queue", "activity_list", "report_context", "report_html_guard_result", "formatted_output_path"))`。
    - `before_tool_call`：非抑制工具 → `await ctx.session.write_custom_stream({"activity-analysis": "tool_progress", "tool": <name>, "status": "running", "args_summary": <dict>})`
    - `after_tool_call`：非抑制工具 → 发 `{"activity-analysis": "tool_progress", ..., "status": "done", "summary": <截断120字>}`；随后读 `ctx.session.get_state(key)` 收集 safe_state_keys 中非空值发 `{"activity-analysis": "state_update", "data": {...}}`（report_context 须剥 `data_snapshot`）。
    - args_summary/summary 的截断规则照抄 v2 sse_bridge `_args_summary`（60 字）/`_summarize_content`（120 字）语义。

- [ ] **Step 1: 写失败测试**

```python
"""ToolCallLimitRail / ToolProgressRail 单元测试（假 ctx，不起 agent）。"""

from types import SimpleNamespace

import pytest

from src.agent_v3.rails import ToolCallLimitRail, ToolProgressRail


class _FakeSession:
    def __init__(self, state=None):
        self._state = state or {}
        self.custom_frames = []

    def get_state(self, key=None):
        return self._state.get(key)

    async def write_custom_stream(self, data):
        self.custom_frames.append(data)


def _tool_ctx(tool_name, session=None, tool_args=None, tool_result=None):
    tool_call = SimpleNamespace(id="call-1")
    return SimpleNamespace(
        extra={},
        session=session,
        inputs=SimpleNamespace(
            tool_name=tool_name,
            tool_args=tool_args or {},
            tool_call=tool_call,
            tool_result=tool_result,
            tool_msg=None,
        ),
    )


async def test_limit_rail_skips_after_max():
    rail = ToolCallLimitRail(max_calls=2)
    await rail.before_invoke(SimpleNamespace(inputs=SimpleNamespace(query="q")))
    for _ in range(2):
        ctx = _tool_ctx("search_activities")
        await rail.before_tool_call(ctx)
        assert ctx.extra.get("_skip_tool") is not True
    ctx3 = _tool_ctx("search_activities")
    await rail.before_tool_call(ctx3)
    assert ctx3.extra["_skip_tool"] is True
    assert "不要再调用" in ctx3.inputs.tool_result
    assert ctx3.inputs.tool_msg is not None


async def test_limit_rail_resets_per_invoke():
    rail = ToolCallLimitRail(max_calls=1)
    await rail.before_invoke(SimpleNamespace(inputs=SimpleNamespace(query="q1")))
    ctx = _tool_ctx("t")
    await rail.before_tool_call(ctx)
    ctx2 = _tool_ctx("t")
    await rail.before_tool_call(ctx2)
    assert ctx2.extra.get("_skip_tool") is True
    # 新一轮 invoke 重置
    await rail.before_invoke(SimpleNamespace(inputs=SimpleNamespace(query="q2")))
    ctx3 = _tool_ctx("t")
    await rail.before_tool_call(ctx3)
    assert ctx3.extra.get("_skip_tool") is not True


async def test_progress_rail_emits_running_done_and_state():
    session = _FakeSession({"analysis_queue": [{"activity_id": "A1"}],
                            "report_context": {"report_id": "r1", "data_snapshot": {"big": 1}}})
    rail = ToolProgressRail()
    await rail.before_tool_call(_tool_ctx("add_to_analysis_queue", session,
                                          tool_args={"activity_ids": ["A1"]}))
    await rail.after_tool_call(_tool_ctx("add_to_analysis_queue", session,
                                         tool_result='{"status":"ok"}'))
    kinds = [f.get("activity-analysis") for f in session.custom_frames]
    assert kinds == ["tool_progress", "tool_progress", "state_update"]
    running, done, state = session.custom_frames
    assert running["status"] == "running" and running["tool"] == "add_to_analysis_queue"
    assert done["status"] == "done"
    assert state["data"]["analysis_queue"] == [{"activity_id": "A1"}]
    # report_context 剥 data_snapshot
    assert "data_snapshot" not in state["data"]["report_context"]


async def test_progress_rail_suppresses_generate_report():
    session = _FakeSession()
    rail = ToolProgressRail()
    await rail.before_tool_call(_tool_ctx("generate_report", session))
    await rail.after_tool_call(_tool_ctx("generate_report", session, tool_result="ok"))
    assert all(f.get("activity-analysis") != "tool_progress" for f in session.custom_frames)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_rails.py -v`
Expected: FAIL（`ToolCallLimitRail` 不存在）

- [ ] **Step 3: 实现**

在 `backend/src/agent_v3/rails.py` 追加（先读 v2 `events/sse_bridge.py` 的 `_args_summary`/`_summarize_content`/`_compact_report_context`，把它们**复制**为模块级私有函数 `_args_summary/_summarize_content/_compact_report_context`——v2 的可直接 import 复用，因为它们在 v2 sse_bridge 里是模块级纯函数；选择 import 复用而非复制）：

```python
from openjiuwen.core.foundation.llm import ToolMessage
from openjiuwen.core.single_agent.rail.base import AgentRail

from src.agent_v2.events.sse_bridge import (
    _args_summary, _compact_report_context, _summarize_content,
)


class ToolCallLimitRail(AgentRail):
    """每轮（一次 invoke）工具调用上限，对标 v2 ToolCallLimitMiddleware(run_limit=8)。"""

    def __init__(self, max_calls: int = 8):
        self._max_calls = max_calls
        self._count = 0

    async def before_invoke(self, ctx) -> None:
        self._count = 0

    async def before_tool_call(self, ctx) -> None:
        self._count += 1
        if self._count <= self._max_calls:
            return
        tool_call = ctx.inputs.tool_call
        tool_call_id = getattr(tool_call, "id", "") if tool_call else ""
        ctx.extra["_skip_tool"] = True
        ctx.inputs.tool_result = (
            f"本轮工具调用次数已达上限（{self._max_calls} 次），本次调用已跳过。"
            "不要再调用该工具，请基于已获得的信息直接回复用户。"
        )
        ctx.inputs.tool_msg = ToolMessage(content=ctx.inputs.tool_result,
                                          tool_call_id=tool_call_id)


class ToolProgressRail(AgentRail):
    """工具进度与业务状态透传：以 custom 流帧发出，由 v3 sse_bridge 转 SSE。

    agent-core 流式无工具开始/结束帧（react_agent 源码确认），进度帧只能由 Rail 自发。
    """

    def __init__(self,
                 suppressed_tools=frozenset({"generate_report"}),
                 safe_state_keys=("analysis_queue", "activity_list", "report_context",
                                  "report_html_guard_result", "formatted_output_path")):
        self._suppressed = suppressed_tools
        self._safe_state_keys = safe_state_keys

    async def before_tool_call(self, ctx) -> None:
        if ctx.inputs.tool_name in self._suppressed or ctx.session is None:
            return
        await ctx.session.write_custom_stream({
            "activity-analysis": "tool_progress",
            "tool": ctx.inputs.tool_name,
            "status": "running",
            "args_summary": _args_summary(ctx.inputs.tool_args),
        })

    async def after_tool_call(self, ctx) -> None:
        if ctx.session is None:
            return
        if ctx.inputs.tool_name not in self._suppressed:
            await ctx.session.write_custom_stream({
                "activity-analysis": "tool_progress",
                "tool": ctx.inputs.tool_name,
                "status": "done",
                "summary": _summarize_content(ctx.inputs.tool_result),
            })
        data = {}
        for key in self._safe_state_keys:
            value = ctx.session.get_state(key)
            if value:
                data[key] = value
        if "report_context" in data:
            data["report_context"] = _compact_report_context(data["report_context"])
        if data:
            await ctx.session.write_custom_stream({"activity-analysis": "state_update", "data": data})
```

注意：`_args_summary`/`_summarize_content`/`_compact_report_context` 在 v2 sse_bridge 中是下划线私有函数——import 私有名跨包使用在本项目属于刻意复用（避免双份漂移），在文件 docstring 注明这一点。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_rails.py tests/agent_v3/test_v3_approval_rail.py -v`
Expected: PASS 9 例

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_v3/rails.py backend/tests/agent_v3/test_v3_rails.py
git commit -m "feat(agent_v3): ToolCallLimitRail 与 ToolProgressRail"
```

---

### Task 7: Agent 单例组装 `agent_v3/agent_factory.py`

**Files:**
- Create: `backend/src/agent_v3/agent_factory.py`
- Test: `backend/tests/agent_v3/test_v3_agent_factory.py`

**Interfaces:**
- Consumes: Task 1 配置项；Task 4 `ALL_V3_TOOLS`；Task 5/6 三个 Rail；v2 `build_system_prompt()`（`src.agent_v2.prompts.system`，框架无关直接复用）；v2 `WRITE_TOOLS`（`src.agent_v2.tools`，审批工具集合）；`get_settings()`。
- Produces（Task 8/9 依赖）:
  - `async def get_v3_agent() -> ReActAgent` — 进程级单例（asyncio.Lock 双检，照 v2 agent_factory 模式）；模型配置读取顺序 `settings.agent_v2_main_llm_{api_key,base_url,model} or settings.llm_{api_key,base_url,model}`；`max_iterations=settings.agent_v3_max_iterations`；注册全部工具（resource_mgr + ability_manager）与三个 Rail；**首次组装时执行 report_gen writer patch**（见下）。
  - `async def close_v3_agent() -> None` — 置空单例；`Runner.stop()` 由 main.py lifespan 统一调（见 Task 10），本函数不重复调。
  - `def patch_report_gen_writer() -> None` — `src.agent_v2.tools.report_gen.get_stream_writer = _v3_get_stream_writer`；`_v3_get_stream_writer()` 返回一个 sync 函数 `write(event)`，其实现为：在调用时经 `get_current_session()` 取会话、`asyncio.get_running_loop()` 取主循环的引用（在工具 async 上下文调用时两者皆可用），`write` 闭包内用 `asyncio.run_coroutine_threadsafe(session.write_custom_stream(dict(event)), loop)`——因为 run_report_pipeline 在 `asyncio.to_thread` 的工作线程里调 writer（v2 report_gen.py:599 实测）。

- [ ] **Step 1: 写失败测试**

```python
"""agent_v3 agent_factory 测试：monkeypatch 重对象，验证组装契约。"""

import asyncio
from types import SimpleNamespace

import pytest

from src.agent_v3 import agent_factory
from src.agent_v3.tools import ALL_V3_TOOLS


def setup_function():
    agent_factory._agent = None


def test_build_model_config_prefers_main_role(monkeypatch):
    settings = SimpleNamespace(
        agent_v2_main_llm_api_key="k1", agent_v2_main_llm_base_url="https://main",
        agent_v2_main_llm_model="m1",
        llm_api_key="gk", llm_base_url="https://global", llm_model="gm",
    )
    client_cfg, request_cfg = agent_factory.build_v3_model_configs(settings)
    assert client_cfg.api_key == "k1"
    assert client_cfg.api_base == "https://main"
    assert request_cfg.model == "m1"


def test_build_model_config_falls_back_to_global(monkeypatch):
    settings = SimpleNamespace(
        agent_v2_main_llm_api_key="", agent_v2_main_llm_base_url="",
        agent_v2_main_llm_model="",
        llm_api_key="gk", llm_base_url="https://global", llm_model="gm",
    )
    client_cfg, request_cfg = agent_factory.build_v3_model_configs(settings)
    assert client_cfg.api_key == "gk"
    assert request_cfg.model == "gm"


async def test_get_v3_agent_registers_tools_and_rails(monkeypatch):
    settings = SimpleNamespace(
        agent_v2_main_llm_api_key="", agent_v2_main_llm_base_url="",
        agent_v2_main_llm_model="",
        llm_api_key="k", llm_base_url="https://x", llm_model="m",
        agent_v3_max_iterations=50,
    )
    monkeypatch.setattr(agent_factory, "get_settings", lambda: settings)
    monkeypatch.setattr(agent_factory, "build_system_prompt", lambda: "sys")
    patched = []
    monkeypatch.setattr(agent_factory, "patch_report_gen_writer",
                        lambda: patched.append(True))
    agent = await agent_factory.get_v3_agent()
    assert agent is not None
    assert patched == [True]
    # 单例
    again = await agent_factory.get_v3_agent()
    assert again is agent
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_agent_factory.py -v`
Expected: FAIL（`No module named 'src.agent_v3.agent_factory'`）

- [ ] **Step 3: 实现**

`backend/src/agent_v3/agent_factory.py`：

```python
"""agent_v3 ReActAgent 进程级单例组装（镜像 v2 agent_factory 模式）。

openjiuwen 导入隔离：全仓库仅 agent_v3 包内允许 import openjiuwen。
"""
from __future__ import annotations

import asyncio
import logging

from openjiuwen.core.foundation.llm import ModelClientConfig, ModelRequestConfig
from openjiuwen.core.runner import Runner
from openjiuwen.core.session import get_current_session
from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig

from src.agent_v2.prompts.system import build_system_prompt
from src.agent_v2.tools import WRITE_TOOLS
from src.agent_v3.rails import ApprovalEditRail, ToolCallLimitRail, ToolProgressRail
from src.agent_v3.tools import ALL_V3_TOOLS
from src.config import get_settings

logger = logging.getLogger("activity-analysis.agent")

_MAX_TOOL_CALLS_PER_RUN = 8


def build_v3_model_configs(settings) -> tuple[ModelClientConfig, ModelRequestConfig]:
    """模型配置：agent_v2_main 角色优先，缺省回退全局 llm_*（与 get_llm 同语义）。"""
    client_cfg = ModelClientConfig(
        client_provider="OpenAI",
        api_key=settings.agent_v2_main_llm_api_key or settings.llm_api_key,
        api_base=settings.agent_v2_main_llm_base_url or settings.llm_base_url,
        timeout=120,
    )
    request_cfg = ModelRequestConfig(
        model=settings.agent_v2_main_llm_model or settings.llm_model,
        temperature=0.1,
    )
    return client_cfg, request_cfg


def patch_report_gen_writer() -> None:
    """把 v2 generate_report 内的 langgraph get_stream_writer 替换为 v3 桥。

    v2 report_gen 在 asyncio.to_thread 工作线程里调 writer（同步函数）；
    这里在工具 async 上下文取会话与主事件循环，write 闭包经
    run_coroutine_threadsafe 把进度帧写回 agent-core custom 流。
    进程级 patch；仅在 AGENT_V3_ENABLED 路径下由 get_v3_agent 触发，
    此时 v2 运行时不会被路由层触达，互不影响。
    """
    from src.agent_v2.tools import report_gen as v2_report_gen

    def _v3_get_stream_writer():
        session = get_current_session()
        loop = asyncio.get_running_loop()

        def write(event) -> None:
            asyncio.run_coroutine_threadsafe(
                session.write_custom_stream(dict(event)), loop)

        return write

    v2_report_gen.get_stream_writer = _v3_get_stream_writer
    logger.info("agent_v3 已 patch report_gen.get_stream_writer")


_agent: ReActAgent | None = None
_lock = asyncio.Lock()


async def get_v3_agent() -> ReActAgent:
    global _agent
    if _agent is not None:
        return _agent
    async with _lock:
        if _agent is not None:
            return _agent
        settings = get_settings()
        client_cfg, request_cfg = build_v3_model_configs(settings)
        config = ReActAgentConfig(
            model_config_obj=request_cfg,
            model_client_config=client_cfg,
            prompt_template=[{"role": "system", "content": build_system_prompt()}],
            max_iterations=settings.agent_v3_max_iterations,
        )
        agent = ReActAgent(card=AgentCard(
            id="activity-analysis-marketing-agent-v3",
            description="营销分析助手 v3",
        )).configure(config)
        for t in ALL_V3_TOOLS:
            Runner.resource_mgr.add_tool(t)
            agent.ability_manager.add(t.card)
        await agent.register_rail(ApprovalEditRail(tool_names=sorted(WRITE_TOOLS)))
        await agent.register_rail(ToolCallLimitRail(max_calls=_MAX_TOOL_CALLS_PER_RUN))
        await agent.register_rail(ToolProgressRail())
        patch_report_gen_writer()
        _agent = agent
        logger.info("agent_v3 ReActAgent initialized, tools=%s",
                    [t.card.name for t in ALL_V3_TOOLS])
        return _agent


async def close_v3_agent() -> None:
    """main.py lifespan shutdown 调用（Runner.stop 由 lifespan 统一负责）。"""
    global _agent
    _agent = None
```

注意：`test_get_v3_agent_registers_tools_and_rails` 会真实构造 ReActAgent（离线可构造，不触网）并真实注册工具——若 `Runner.resource_mgr.add_tool` 在 Runner 未 start 时抛错，测试里先 `monkeypatch` 掉 `agent_factory.Runner` 为 `SimpleNamespace(resource_mgr=SimpleNamespace(add_tool=lambda t: None))`；以实测行为为准调整测试，不要让测试起 Runner。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_agent_factory.py -v`
Expected: PASS 3 例

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_v3/agent_factory.py backend/tests/agent_v3/test_v3_agent_factory.py
git commit -m "feat(agent_v3): ReActAgent 单例组装与 report_gen writer 桥接 patch"
```

---

### Task 8: SSE 桥 `agent_v3/events/sse_bridge.py`

**Files:**
- Create: `backend/src/agent_v3/events/__init__.py`（空 docstring 即可）
- Create: `backend/src/agent_v3/events/sse_bridge.py`
- Test: `backend/tests/agent_v3/test_v3_sse_bridge.py`

**Interfaces:**
- Consumes: Task 2 `read_business_state / set_pending_interrupt / clear_pending_interrupt`；v2 sse_bridge 的纯帧构造函数 `tool_progress_frame / pipeline_step_frame / frame / _frame`（import 复用）与 `TOOL_DISPLAY_NAMES`。
- Produces（Task 9 依赖）:
  - `async def stream_v3_events(agent, session, inputs: dict, request_id: str, thread_id: str, is_cancelled) -> AsyncGenerator[str, None]` — 驱动 `Runner.run_agent_streaming(...)` 并产出与 v2 完全一致的 SSE 帧文本（含终态 done 帧）。
  - `def interaction_to_approval_frame(payload, activities: list[dict]) -> str` — `__interaction__` 帧 payload → approval_required SSE 帧。

帧映射表（P0 实测 + 本计划约定）：

| 输入帧 | SSE 输出 |
|---|---|
| `OutputSchema type=llm_output` | 不直接输出；累计 `content` 拼 final_response |
| `OutputSchema type=llm_reasoning` / `llm_usage` / `tracer_*` | 忽略 |
| `OutputSchema type=answer` | 记 `payload["output"]` 为最终答案（优先于累计值）；循环结束后发 done 帧 |
| `OutputSchema type=__interaction__` | approval_required 帧 + `set_pending_interrupt(thread_id, payload.id)` |
| `CustomSchema {"activity-analysis": "tool_progress", ...}` | `tool_progress_frame(tool, status, summary, args_summary)` |
| `CustomSchema {"activity-analysis": "state_update", "data": {...}}` | `frame("node_update", data)`；其中 `formatted_output_path`→export_artifact 转换逻辑照 v2（见下） |
| `CustomSchema {"step": ..., "status": ...}` | `pipeline_step_frame(step, status)`（generate_report 管线进度） |
| `is_cancelled()` 为真 | `cancelled` 帧并 return |

done 帧组装（与 v2 sse_bridge.py:361-376 字段完全一致）：
- `final_response`：answer 帧 output 优先，否则 llm_output 累计。
- `html_report / analysis_queue / report_context`：`read_business_state(thread_id)`，report_context 剥 `data_snapshot`。
- `report_updated`：本轮 state_update 帧中出现过非空 html_report，或终态 html_report 与起始不同——简化为：本轮任一 state_update 含 `report_html_guard_result` 或工具 modify_report/generate_report 的 done 帧出现过即为 True（在 CustomSchema 处理处打标）。
- `export_artifact`：state_update 的 `formatted_output_path` 处理照 v2 sse_bridge.py:331-337 语义——仅当本轮 export_report 成功（其 tool_progress done 帧 summary 非 ERROR 开头）才把 formatted_output_path 转 `{kind, file_name, format, download_url}`（复用 v2 `_export_artifact`）。
- `awaiting_approval`：本轮出现过 `__interaction__`。
- `tool_calls_count`：本轮 tool_progress running 帧计数。

approval_required 帧 payload（对齐 v2 sse_bridge.py:130-154）：`{tool, args, description, allowed_decisions: ["approve","edit","reject"], display_name, activities}`；args 从 `payload.payload.tool_args`（JSON 字符串须 `json.loads`，失败给 `{}`）；description 用 `payload.payload.message`；activities 对 `add_to_analysis_queue` 经 `read_business_state(thread_id)["activity_list"]` 把 activity_id 解析为 `{activity_id, name, row_number}`（复用 v2 `activity_key/activity_name`，逻辑照 v2 sse_bridge.py:157-195，但数据源从 graph state 改为会话状态）。

- [ ] **Step 1: 写失败测试**

```python
"""v3 sse_bridge 帧映射测试：罐头帧序列 → 断言 SSE 帧文本。"""

import json
from types import SimpleNamespace

import pytest
from openjiuwen.core.session.stream.base import CustomSchema, OutputSchema

from src.agent_v3 import sessions as v3_sessions
from src.agent_v3.events import sse_bridge as v3_bridge


class _FakeRunnerStream:
    """模拟 Runner.run_agent_streaming 的异步帧序列。"""

    def __init__(self, chunks):
        self._chunks = chunks

    def __call__(self, agent, inputs, *, session=None, stream_modes=None):
        async def gen():
            for c in self._chunks:
                yield c
        return gen()


def _out(t, payload):
    return OutputSchema(type=t, index=0, payload=payload)


def _custom(data):
    return CustomSchema(**data)


def _parse(frame_text):
    assert frame_text.startswith("data: ")
    return json.loads(frame_text[len("data: "):])


async def _collect(chunks, thread_id="t1"):
    orig = v3_bridge.Runner.run_agent_streaming
    v3_bridge.Runner.run_agent_streaming = _FakeRunnerStream(chunks)
    try:
        frames = []
        async for f in v3_bridge.stream_v3_events(
                agent=None, session=None, inputs={"query": "hi"},
                request_id="r1", thread_id=thread_id, is_cancelled=lambda: False):
            frames.append(_parse(f))
        return frames
    finally:
        v3_bridge.Runner.run_agent_streaming = orig


def setup_function():
    v3_sessions.reset_sessions()


async def test_llm_output_and_answer_to_done():
    frames = await _collect([
        _out("llm_output", {"content": "你", "result_type": "stream"}),
        _out("llm_output", {"content": "好", "result_type": "stream"}),
        _out("llm_usage", {"total_tokens": 10}),
        _out("answer", {"output": "你好", "result_type": "answer"}),
    ])
    done = frames[-1]
    assert done["type"] == "done"
    assert done["payload"]["final_response"] == "你好"
    assert done["payload"]["awaiting_approval"] is False
    assert done["payload"]["request_id"] == "r1"


async def test_interaction_to_approval_and_pending():
    interaction_payload = SimpleNamespace(
        id="int-1",
        payload=SimpleNamespace(
            tool_name="modify_report",
            tool_call_id="call-1",
            tool_args='{"free_instruction":"改标题"}',
            message="请确认是否执行该操作",
        ),
    )
    frames = await _collect([_out("__interaction__", interaction_payload)])
    approval = frames[0]
    assert approval["type"] == "approval_required"
    assert approval["payload"]["tool"] == "modify_report"
    assert approval["payload"]["args"] == {"free_instruction": "改标题"}
    assert approval["payload"]["allowed_decisions"] == ["approve", "edit", "reject"]
    assert v3_sessions.get_pending_interrupt("t1") == "int-1"
    done = frames[-1]
    assert done["payload"]["awaiting_approval"] is True


async def test_custom_tool_progress_and_state_update():
    frames = await _collect([
        _custom({"activity-analysis": "tool_progress", "tool": "search_activities",
                 "status": "running", "args_summary": {"keyword": "贷款"}}),
        _custom({"activity-analysis": "tool_progress", "tool": "search_activities",
                 "status": "done", "summary": "3 条"}),
        _custom({"activity-analysis": "state_update", "data": {"activity_list": [{"activity_id": "A1"}]}}),
        _custom({"step": "marketing_report_synthesis", "status": "running"}),
        _out("answer", {"output": "ok", "result_type": "answer"}),
    ])
    types = [f["type"] for f in frames]
    assert types == ["node_update", "node_update", "node_update", "node_update", "done"]
    assert frames[0]["node"] == "search_activities"
    assert frames[0]["payload"]["tool_status"] == "running"
    assert frames[1]["payload"]["tool_status"] == "done"
    assert frames[2]["payload"]["activity_list"] == [{"activity_id": "A1"}]
    assert frames[3]["node"] == "marketing_report_synthesis"
    assert frames[-1]["payload"]["tool_calls_count"] == 1


async def test_cancel_emits_cancelled_frame():
    chunks = [_out("llm_output", {"content": "x", "result_type": "stream"})]

    class _CancelStream(_FakeRunnerStream):
        def __call__(self, agent, inputs, *, session=None, stream_modes=None):
            async def gen():
                yield self._chunks[0]
                yield self._chunks[0]  # 第二帧消费前 is_cancelled 已为真
            return gen()

    calls = {"n": 0}

    def is_cancelled():
        calls["n"] += 1
        return calls["n"] > 1

    monkeypatch_target = v3_bridge.Runner
    orig = monkeypatch_target.run_agent_streaming
    monkeypatch_target.run_agent_streaming = _CancelStream(chunks)
    try:
        frames = []
        async for f in v3_bridge.stream_v3_events(
                agent=None, session=None, inputs={"query": "hi"},
                request_id="r1", thread_id="t1", is_cancelled=is_cancelled):
            frames.append(_parse(f))
    finally:
        monkeypatch_target.run_agent_streaming = orig
    assert frames[-1]["type"] == "cancelled"
```

注意：`Runner` 是类属性替换（`v3_bridge.Runner.run_agent_streaming = ...`），`Runner` 在 openjiuwen 里是带类方法的类，替换其属性对本测试文件内的调用有效，且每个测试经 `try/finally` 恢复原值。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_sse_bridge.py -v`
Expected: FAIL（`No module named 'src.agent_v3.events'`）

- [ ] **Step 3: 实现**

`backend/src/agent_v3/events/sse_bridge.py`：

```python
"""agent-core 流帧 → SSE 帧桥接（帧契约与 v2 完全一致，前端零改动）。"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Callable

from openjiuwen.core.runner import Runner
from openjiuwen.core.session.stream.base import BaseStreamMode, CustomSchema, OutputSchema

from src.agent_v2.events.sse_bridge import (
    _compact_report_context, _export_artifact, _frame,
    pipeline_step_frame, tool_progress_frame,
)
from src.agent_v2.tools import TOOL_DISPLAY_NAMES
from src.agent_v2.tools._common import activity_key, activity_name
from src.agent_v3 import sessions as v3_sessions

logger = logging.getLogger("activity-analysis.agent")

_STREAM_MODES = [BaseStreamMode.OUTPUT, BaseStreamMode.CUSTOM]


def _llm_content(payload: Any) -> str:
    if isinstance(payload, dict):
        return str(payload.get("content") or "")
    if isinstance(payload, tuple) and len(payload) == 2 and isinstance(payload[1], dict):
        return str(payload[1].get("content") or "")
    return ""


def interaction_to_approval_frame(payload: Any, thread_id: str) -> str:
    """__interaction__ 帧 payload → approval_required SSE 帧（对齐 v2 帧结构）。"""
    request = getattr(payload, "payload", None)
    tool = str(getattr(request, "tool_name", "") or "")
    raw_args = getattr(request, "tool_args", None)
    args: dict = {}
    if isinstance(raw_args, dict):
        args = raw_args
    elif isinstance(raw_args, str) and raw_args.strip():
        try:
            args = json.loads(raw_args)
        except (TypeError, ValueError):
            args = {}
    activities = []
    if tool == "add_to_analysis_queue":
        ids = args.get("activity_ids") or []
        by_id = {
            activity_key(item): item
            for item in v3_sessions.read_business_state(thread_id)["activity_list"]
            if isinstance(item, dict)
        }
        activities = [
            {
                "activity_id": aid,
                "name": activity_name(by_id.get(aid)) if by_id.get(aid) else aid,
                "row_number": (by_id.get(aid, {}) or {}).get("row_number"),
            }
            for aid in ids
        ]
    message = {
        "type": "approval_required",
        "payload": {
            "tool": tool,
            "args": args,
            "description": str(getattr(request, "message", "") or ""),
            "allowed_decisions": ["approve", "edit", "reject"],
            "display_name": TOOL_DISPLAY_NAMES.get(tool, tool),
            "activities": activities,
        },
    }
    return _frame(message)


async def stream_v3_events(
    agent,
    session,
    inputs: dict,
    request_id: str,
    thread_id: str,
    is_cancelled: Callable[[], bool],
) -> AsyncGenerator[str, None]:
    """驱动 Runner.run_agent_streaming 并产出 SSE 帧（帧契约同 v2）。"""
    answer_output = ""
    accumulated: list[str] = []
    saw_interrupt = False
    report_updated = False
    tool_calls_count = 0
    export_succeeded = False
    export_artifact: dict = {}

    async for chunk in Runner.run_agent_streaming(
            agent, inputs, session=session, stream_modes=_STREAM_MODES):
        if is_cancelled():
            yield _frame({"type": "cancelled", "payload": {}})
            return

        if isinstance(chunk, CustomSchema):
            data = chunk.model_dump()
            marker = data.pop("activity-analysis", None)
            if marker == "tool_progress":
                tool = str(data.get("tool") or "")
                status = str(data.get("status") or "")
                if status == "running":
                    tool_calls_count += 1
                if tool == "export_report" and status == "done" \
                        and not str(data.get("summary") or "").startswith("ERROR:"):
                    export_succeeded = True
                if tool in {"generate_report", "modify_report"} and status == "done":
                    report_updated = True
                yield tool_progress_frame(tool, status,
                                          summary=str(data.get("summary") or ""),
                                          args_summary=data.get("args_summary") or None)
            elif marker == "state_update":
                state_data = dict(data.get("data") or {})
                if "report_html_guard_result" in state_data:
                    report_updated = True
                formatted = state_data.pop("formatted_output_path", None)
                if formatted and export_succeeded:
                    artifact = _export_artifact(formatted)
                    if artifact:
                        export_artifact = artifact
                        state_data["export_artifact"] = artifact
                if state_data:
                    yield _frame({"type": "node_update", "payload": state_data})
            elif "step" in data:
                yield pipeline_step_frame(str(data.get("step")),
                                          str(data.get("status") or "running"))
            continue

        if not isinstance(chunk, OutputSchema):
            continue

        if chunk.type == "llm_output":
            accumulated.append(_llm_content(chunk.payload))
        elif chunk.type == "answer":
            payload = chunk.payload if isinstance(chunk.payload, dict) else {}
            answer_output = str(payload.get("output") or "")
        elif chunk.type == "__interaction__":
            saw_interrupt = True
            interrupt_id = str(getattr(chunk.payload, "id", "") or "")
            if interrupt_id:
                v3_sessions.set_pending_interrupt(thread_id, interrupt_id)
            yield interaction_to_approval_frame(chunk.payload, thread_id)
        # llm_reasoning / llm_usage / tracer_*：忽略

    business = v3_sessions.read_business_state(thread_id)
    if export_succeeded and not export_artifact:
        export_artifact = _export_artifact(business.get("formatted_output_path"))
    yield _frame({
        "type": "done",
        "payload": {
            "request_id": request_id,
            "final_response": answer_output or "".join(accumulated),
            "html_report": business["html_report"],
            "analysis_queue": business["analysis_queue"],
            "report_context": _compact_report_context(business["report_context"]),
            "export_artifact": export_artifact,
            "report_updated": report_updated,
            "awaiting_approval": saw_interrupt,
            "tool_calls_count": tool_calls_count,
        },
    })
```

注意：
- v2 的 `_export_artifact`/`_compact_report_context`/`_frame`/`tool_progress_frame`/`pipeline_step_frame` 均为模块级纯函数，直接 import 复用（跨包私有名复用是有意为之，防双份漂移）。
- `CustomSchema` 是 extra="allow" 的 pydantic 模型，`chunk.model_dump()` 拿到原 dict（`step`/`status` 或 `activity-analysis` 标记）。
- `tool_progress_frame` 的 v2 签名是 `(tool, status, summary="", args_summary=None)`，args_summary 为 None 时 v2 实现会跳过该键——核对 v2 源码确认传参兼容。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_sse_bridge.py -v`
Expected: PASS 4 例

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_v3/events/ backend/tests/agent_v3/test_v3_sse_bridge.py
git commit -m "feat(agent_v3): agent-core 流帧 → SSE 桥接（帧契约同 v2）"
```

---

### Task 9: 运行时 `agent_v3/runtime.py`（含审批恢复与缓冲重连）

**Files:**
- Create: `backend/src/agent_v3/runtime.py`
- Test: `backend/tests/agent_v3/test_v3_runtime.py`

**Interfaces:**
- Consumes: Task 7 `get_v3_agent`；Task 8 `stream_v3_events`；Task 2 sessions 模块；v2 `record_turn_start/finish_turn`、`set_request_context/reset_request_context`、`get_settings`。
- Produces（Task 10 路由层依赖，签名与 v2 runtime 完全一致）:
  - `async def stream_agent_run(thread_id, message, original_user_text="", file_path="", user_id="", user_name="", org_no="", src_sys_no="", channel="") -> AsyncGenerator[str, None]`
  - `async def stream_agent_resume(thread_id, decision, tool="", edited_args=None, message="", user_id="", user_name="", org_no="", src_sys_no="", channel="") -> AsyncGenerator[str, None]`
  - `async def start_buffered_agent_run(**kwargs)` / `async def start_buffered_agent_resume(**kwargs)`
  - `def get_buffered_run_status(thread_id) -> dict` / `def attach_buffered_agent_run(thread_id, after=0)` / `def request_cancel(thread_id) -> bool`

实现要点：
1. **`_BufferedRun` / `_start_buffered_run` / 过期清理 / 冲突帧**：整段从 v2 runtime.py:37-143 平移（框架无关，一字不改，注意把模块内 `_frame` 一起带过来）。
2. **`stream_agent_run`**：照 v2 runtime.py:169-273 结构——cancel 注册表、set_request_context（含 `uploaded_file_path: file_path`）、record_turn_start（messages 字段传 `[{"role": "user", "content": message}]` 结构前先读 `conversation_log_service._original_user_text` 确认它能否解析非 langchain 消息；若不能则改为只传 `original_user_text`——以源码为准）、`session = v3_sessions.get_or_create_session(thread_id)`、`agent = await get_v3_agent()`、调 `stream_v3_events(agent, session, {"query": message}, ...)`；帧扫描置 `final_status`（`cancelled` / `awaiting_approval` 判定字符串与 v2 相同）；finish_turn/异常/finally 清理全同 v2。
3. **`stream_agent_resume`**：
   - decision 校验 ∈ {approve, edit, reject}，无效 → error 帧（文案同 v2）。
   - `interrupt_id = v3_sessions.get_pending_interrupt(thread_id)`；为 None → `error` 帧 `"该会话没有待审批的操作"`。
   - 构造 payload：`{"decision": decision}`；edit 时 `payload["edited_args"] = edited_args or {}`；reject 时 `payload["message"] = message or "用户拒绝了该操作"`。
   - `ii = InteractiveInput(); ii.update(interrupt_id, payload)`；`v3_sessions.clear_pending_interrupt(thread_id)` 后 `stream_v3_events(agent, session, {"query": ii}, ...)`。**新一轮若再出 `__interaction__`（reject 后模型重试），bridge 会自动 set 新 pending id——天然支持二次审批，无需额外代码。**
   - 审计：record_turn_start 的 messages 内容用 `f"已审批 {tool}：{decision}"`（同 v2）。
4. **取消**：`request_cancel(thread_id)` 置事件；bridge 在帧间隙检查（同 v2 粒度）；run 结束 finally 里 `_cancelled.pop`。另外对缓冲 run 的驱动 task，在 emit cancelled 后任务自然结束（generator return）。不调用 `agent.abort()`（P0 只发现提前 break 有 ContextVar 告警；帧间隙停止消费即可，告警无害）——若联调发现取消后工具仍在执行副作用，再补 `await agent.abort()`（BaseAgent 有该方法则调）。

- [ ] **Step 1: 写失败测试**

```python
"""agent_v3 runtime 测试：monkeypatch bridge/agent，验证审计、取消、resume 契约。"""

import json
from types import SimpleNamespace

import pytest

from src.agent_v3 import runtime as v3_runtime
from src.agent_v3 import sessions as v3_sessions


def _parse(frame_text):
    line = frame_text.split("\n")[0]
    if line.startswith("id: "):
        line = frame_text.split("\n")[1]
    assert line.startswith("data: ")
    return json.loads(line[len("data: "):])


def setup_function():
    v3_sessions.reset_sessions()
    v3_runtime._cancelled.clear()
    v3_runtime._buffered_runs.clear()


@pytest.fixture
def fake_deps(monkeypatch):
    calls = {"turn_start": [], "turn_finish": []}
    monkeypatch.setattr(v3_runtime, "record_turn_start",
                        lambda s: calls["turn_start"].append(s))
    monkeypatch.setattr(v3_runtime, "finish_turn",
                        lambda *a, **k: calls["turn_finish"].append((a, k)))
    monkeypatch.setattr(v3_runtime, "get_v3_agent", _fake_agent)
    monkeypatch.setattr(v3_sessions, "create_agent_session",
                        lambda session_id=None: SimpleNamespace(
                            session_id=session_id, get_state=lambda k=None: None,
                            update_state=lambda d: None))
    return calls


async def _fake_agent():
    return SimpleNamespace()


def _fake_stream(frames):
    async def gen(**kwargs):
        for f in frames:
            yield f
    return gen


async def test_run_emits_frames_and_audit(fake_deps, monkeypatch):
    monkeypatch.setattr(v3_runtime, "stream_v3_events",
                        lambda **kw: _fake_stream([
                            'data: {"type": "done", "payload": {}}\n\n'])())
    frames = []
    async for f in v3_runtime.stream_agent_run(thread_id="t1", message="你好"):
        frames.append(f)
    assert _parse(frames[-1])["type"] == "done"
    assert len(fake_deps["turn_start"]) == 1
    assert fake_deps["turn_start"][0]["thread_id"] == "t1"
    status = fake_deps["turn_finish"][0][0][1]
    assert status == "success"


async def test_resume_without_pending_interrupt_errors(fake_deps):
    frames = []
    async for f in v3_runtime.stream_agent_resume(thread_id="t1", decision="approve"):
        frames.append(f)
    assert _parse(frames[-1])["type"] == "error"


async def test_resume_builds_interactive_input(fake_deps, monkeypatch):
    seen = {}

    async def spy_stream(agent, session, inputs, **kw):
        seen["inputs"] = inputs
        yield 'data: {"type": "done", "payload": {}}\n\n'

    monkeypatch.setattr(v3_runtime, "stream_v3_events", spy_stream)
    v3_sessions.set_pending_interrupt("t1", "int-9")
    frames = []
    async for f in v3_runtime.stream_agent_resume(
            thread_id="t1", decision="edit", tool="modify_report",
            edited_args={"free_instruction": "改"}):
        frames.append(f)
    ii = seen["inputs"]["query"]
    assert ii.user_inputs["int-9"]["decision"] == "edit"
    assert ii.user_inputs["int-9"]["edited_args"] == {"free_instruction": "改"}
    assert v3_sessions.get_pending_interrupt("t1") is None


async def test_resume_rejects_bad_decision(fake_deps):
    frames = []
    async for f in v3_runtime.stream_agent_resume(thread_id="t1", decision="maybe"):
        frames.append(f)
    assert _parse(frames[-1])["type"] == "error"


async def test_duplicate_run_conflict(fake_deps, monkeypatch):
    async def slow_stream(**kw):
        import asyncio
        yield 'data: {"type": "node_update", "payload": {}}\n\n'
        await asyncio.sleep(5)

    monkeypatch.setattr(v3_runtime, "stream_v3_events", lambda **kw: slow_stream())
    s1 = await v3_runtime.start_buffered_agent_run(thread_id="t1", message="a")
    first = await s1.__anext__()
    assert _parse(first)["type"] == "node_update"
    s2 = await v3_runtime.start_buffered_agent_run(thread_id="t1", message="b")
    conflict = await s2.__anext__()
    assert _parse(conflict)["type"] == "error"
    v3_runtime.request_cancel("t1")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_runtime.py -v`
Expected: FAIL（`No module named 'src.agent_v3.runtime'`）

- [ ] **Step 3: 实现**

`backend/src/agent_v3/runtime.py`：从 v2 runtime.py 平移 `_BufferedRun`/`_buffered_runs`/`_expire_buffered_run`/`_drive_buffered_run`/`_start_buffered_run`/`start_buffered_agent_run`/`start_buffered_agent_resume`/`get_buffered_run_status`/`attach_buffered_agent_run`/`request_cancel`/`_frame`/`_cancelled`，然后实现两个驱动函数：

```python
"""agent_v3 运行时：请求驱动、取消注册表、审计（契约与 v2 runtime 完全一致）。"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncGenerator
from uuid import uuid4

from openjiuwen.core.session import InteractiveInput

from src.agent_v3 import sessions as v3_sessions
from src.agent_v3.agent_factory import get_v3_agent
from src.agent_v3.events.sse_bridge import stream_v3_events
from src.agent_v2.state.request_context import (
    reset_request_context, set_request_context,
)
from src.services.conversation_log_service import finish_turn, record_turn_start

logger = logging.getLogger("activity-analysis.agent")

# ── 以下整段从 agent_v2/runtime.py 平移（_BufferedRun/缓冲注册表/取消/帧函数），
#    逐字拷贝 v2 runtime.py:34-158 的实现，仅改动 docstring 引用 ──
```

（平移后）`stream_agent_run`：

```python
async def stream_agent_run(
    thread_id: str,
    message: str,
    original_user_text: str = "",
    file_path: str = "",
    user_id: str = "",
    user_name: str = "",
    org_no: str = "",
    src_sys_no: str = "",
    channel: str = "",
) -> AsyncGenerator[str, None]:
    if thread_id in _cancelled:
        yield _frame("error", {"message": "该会话已有正在运行的任务，请先停止或等待完成"})
        return

    request_id = uuid4().hex
    started = time.monotonic()
    cancel_event = asyncio.Event()
    _cancelled[thread_id] = cancel_event
    ctx_token = set_request_context({
        "user_id": user_id, "user_name": user_name, "org_no": org_no,
        "src_sys_no": src_sys_no, "channel": channel,
        "uploaded_file_path": file_path, "thread_id": thread_id,
        "request_id": request_id,
    })

    try:
        record_turn_start({
            "request_id": request_id, "thread_id": thread_id,
            "user_id": user_id, "user_name": user_name, "channel": channel,
            "original_user_text": original_user_text or message,
        })

        agent = await get_v3_agent()
        session = v3_sessions.get_or_create_session(thread_id)

        final_status = "success"
        failure_reason = ""
        async for frame_text in stream_v3_events(
            agent=agent, session=session, inputs={"query": message},
            request_id=request_id, thread_id=thread_id,
            is_cancelled=cancel_event.is_set,
        ):
            if '"type": "cancelled"' in frame_text:
                final_status = "cancelled"
                failure_reason = "用户取消任务"
            elif '"type": "approval_required"' in frame_text:
                final_status = "awaiting_approval"
            yield frame_text

        duration_ms = int((time.monotonic() - started) * 1000)
        finish_turn(request_id, final_status, duration_ms, {"final_response": ""},
                    failure_reason=failure_reason)
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.exception("agent_v3 run 异常: thread=%s request=%s", thread_id, request_id)
        finish_turn(request_id, "failed", duration_ms, failure_reason=str(exc)[:500])
        yield _frame("error", {"message": str(exc)[:300]})
    finally:
        _cancelled.pop(thread_id, None)
        reset_request_context(ctx_token)
```

`stream_agent_resume`：

```python
async def stream_agent_resume(
    thread_id: str,
    decision: str,
    tool: str = "",
    edited_args: dict | None = None,
    message: str = "",
    user_id: str = "",
    user_name: str = "",
    org_no: str = "",
    src_sys_no: str = "",
    channel: str = "",
) -> AsyncGenerator[str, None]:
    if decision not in {"approve", "edit", "reject"}:
        yield _frame("error", {"message": f"无效的审批决策：{decision}"})
        return

    interrupt_id = v3_sessions.get_pending_interrupt(thread_id)
    if not interrupt_id:
        yield _frame("error", {"message": "该会话没有待审批的操作"})
        return

    request_id = uuid4().hex
    started = time.monotonic()
    audit_text = f"已审批 {tool}：{decision}"
    ctx_token = set_request_context({
        "user_id": user_id, "user_name": user_name, "org_no": org_no,
        "src_sys_no": src_sys_no, "channel": channel,
        "uploaded_file_path": "", "thread_id": thread_id,
        "request_id": request_id,
    })

    try:
        record_turn_start({
            "request_id": request_id, "thread_id": thread_id,
            "user_id": user_id, "user_name": user_name, "channel": channel,
            "original_user_text": message or audit_text,
        })

        payload: dict = {"decision": decision}
        if decision == "edit":
            payload["edited_args"] = edited_args or {}
        elif decision == "reject":
            payload["message"] = message or "用户拒绝了该操作"

        interactive = InteractiveInput()
        interactive.update(interrupt_id, payload)
        v3_sessions.clear_pending_interrupt(thread_id)

        agent = await get_v3_agent()
        session = v3_sessions.get_or_create_session(thread_id)

        async for frame_text in stream_v3_events(
            agent=agent, session=session, inputs={"query": interactive},
            request_id=request_id, thread_id=thread_id,
            is_cancelled=lambda: False,
        ):
            yield frame_text

        duration_ms = int((time.monotonic() - started) * 1000)
        finish_turn(request_id, "success", duration_ms, {"final_response": ""})
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.exception("agent_v3 resume 异常: thread=%s request=%s", thread_id, request_id)
        finish_turn(request_id, "failed", duration_ms, failure_reason=str(exc)[:500])
        yield _frame("error", {"message": str(exc)[:300]})
    finally:
        reset_request_context(ctx_token)
```

注意（实现前必读）：先打开 `src/services/conversation_log_service.py` 与 `agent_run_history_service._original_user_text`，确认 record_turn_start 的 state dict 在**没有 messages 键**时 user_text 提取是否正常（v2 传了 langchain HumanMessage 列表；v3 不应 import langchain 消息类型——若 `_original_user_text` 只认消息列表，则构造最小 duck 对象 `SimpleNamespace(content=message, type="human")` 或直接确认 `original_user_text` 优先路径已足够）。以此源码事实为准，并在测试断言里覆盖。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/ -v`
Expected: 全部 PASS（含此前 task 的 20+ 例无回归）

- [ ] **Step 5: 同时跑 v2 全量测试确认零改动**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v2/ -v`
Expected: 与基线一致（注意：memory 记录 `test_tools_report_export` 有 2 例 M3 既有失败，非回归——与基线对比即可）

- [ ] **Step 6: Commit**

```bash
git add backend/src/agent_v3/runtime.py backend/tests/agent_v3/test_v3_runtime.py
git commit -m "feat(agent_v3): 运行时（run/resume/缓冲重连/取消/审计）"
```

---

### Task 10: 路由开关接入 + lifespan

**Files:**
- Modify: `backend/src/api/routers/agent_v2.py`（每个端点加分流，约 :39-106）
- Modify: `backend/src/main.py`（lifespan，约 :150-202）
- Test: `backend/tests/agent_v3/test_v3_router.py`

**Interfaces:**
- Consumes: Task 9 的全部 runtime 函数（签名与 v2 一致）；Task 1 `agent_v3_enabled` 开关。
- Produces: `AGENT_V3_ENABLED=true` 时 `/api/v2/agent/*` 五端点全部走 v3 runtime；false 时行为逐字节不变。

- [ ] **Step 1: 写失败测试**

```python
"""路由分流测试：开关打开时 /v2/agent/* 委托 v3 runtime。"""

from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from src.agent_v3 import runtime as v3_runtime


def _settings(enabled):
    return SimpleNamespace(agent_v3_enabled=enabled)


async def _fake_stream(**kwargs):
    yield 'data: {"type": "done", "payload": {}}\n\n'


async def test_run_delegates_to_v3_when_enabled(monkeypatch):
    from src.api.routers import agent_v2 as router_mod

    calls = []
    monkeypatch.setattr(router_mod, "get_settings", lambda: _settings(True))

    async def spy(**kwargs):
        calls.append(kwargs)
        async for f in _fake_stream(**kwargs):
            yield f

    monkeypatch.setattr(v3_runtime, "start_buffered_agent_run", spy)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router_mod.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/agent/run", json={"thread_id": "t1", "message": "hi"})
    assert resp.status_code == 200
    assert calls and calls[0]["thread_id"] == "t1"
```

注意：先读 `backend/src/api/routers/agent_v2.py` 确认 router 前缀（应为 `/v2/agent` 或经 include 加前缀）与 get_settings 的 import 方式（`from src.config import get_settings` → monkeypatch `router_mod.get_settings` 有效）；测试 URL 前缀以源码实际为准。若 v2 端点当前没用 get_settings，则分流判断改为 `from src.config import get_settings` 在函数内调用，测试按上述 monkeypatch。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/test_v3_router.py -v`
Expected: FAIL（分流逻辑不存在，calls 为空或断言失败）

- [ ] **Step 3: 实现分流**

在 `backend/src/api/routers/agent_v2.py` 顶部 import 区加 `from src.config import get_settings`（若已有则跳过），五个端点（run / resume / cancel / runs 状态 / runs stream 续接）各加分流，模式：

```python
@router.post("/run")
async def run_agent(req: AgentRunRequest):
    if get_settings().agent_v3_enabled:
        from src.agent_v3 import runtime as v3_runtime
        stream = await v3_runtime.start_buffered_agent_run(**req.model_dump())
    else:
        stream = await start_buffered_agent_run(**req.model_dump())
    return StreamingResponse(stream, media_type="text/event-stream")
```

（v3 延迟 import 写在分支内，保证开关关闭时 v3 包不被加载、openjiuwen 重依赖不进场。resume/cancel/status/attach 四个端点同构：cancel → `v3_runtime.request_cancel(req.thread_id)`；status → `v3_runtime.get_buffered_run_status(thread_id)`；attach → `v3_runtime.attach_buffered_agent_run(thread_id, after=after)`，None 时 404 与 v2 一致。改前先读现有五个端点实现，保持返回类型/状态码逐字节一致。）

`backend/src/main.py` lifespan：

- startup 段（DB 初始化之后）追加：

```python
    if get_settings().agent_v3_enabled:
        from openjiuwen.core.runner import Runner
        await Runner.start()
        logger.info("agent_v3 enabled: openjiuwen Runner started")
```

- shutdown 段现有 `close_agent()` 调用之后追加：

```python
    if get_settings().agent_v3_enabled:
        from src.agent_v3.agent_factory import close_v3_agent
        from openjiuwen.core.runner import Runner
        await close_v3_agent()
        await Runner.stop()
```

（先读 main.py lifespan 现状，logger 名称/get_settings import 以其现有风格为准。）

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `cd backend && venv/bin/python -m pytest tests/agent_v3/ tests/agent_v2/ -v`
Expected: v3 全 PASS；v2 与基线一致（含 2 例 M3 既有失败）

再验证开关关闭时应用可正常启动（openjiuwen 未被 import）：

```bash
cd backend && venv/bin/python -c "
import sys
from src.main import app
assert not any(m.startswith('openjiuwen') for m in sys.modules), 'openjiuwen 不应在开关关闭时被 import'
print('lazy import ok')
"
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/api/routers/agent_v2.py backend/src/main.py backend/tests/agent_v3/test_v3_router.py
git commit -m "feat(agent_v3): AGENT_V3_ENABLED 路由分流与 lifespan 接入"
```

---

### Task 11: 实机联调验收（live，人工执行）

**Files:**
- Create: `docs/superpowers/specs/2026-08-07-agent-v3-p1-acceptance.md`（验收记录）

**Interfaces:**
- Consumes: 全部前序 task；真实 LLM 端点（`backend/.env`）。

- [ ] **Step 1: 起服务**

```bash
cd backend && AGENT_V3_ENABLED=true venv/bin/python -m uvicorn src.main:app --port 8000
```

另开前端（照项目既有方式），或用 curl 直打 API。

- [ ] **Step 2: 逐项验收并记录**

按顺序执行并在验收文档逐项打勾（每项记录请求/关键帧截图或文本）：

1. 纯问答：发"你好，介绍一下你自己"→ done 帧 final_response 非空。
2. 查询工具：`search_activities` → node_update running/done 帧成对，done 帧 tool_calls_count=1。
3. 写工具审批 approve：让模型 `add_to_analysis_queue` → approval_required 帧（tool/args/display_name/activities 齐全）→ POST /resume approve → 工具真实执行，done 帧 analysis_queue 含该项。
4. 写工具审批 edit：同触发 → resume decision=edit + edited_args 改 activity_ids → 断言队列里是改后的值（**重点验证 new_args JSON 字符串路径真实生效**）。
5. 写工具审批 reject + 二次审批：resume reject → 若模型按 feedback 重试同工具，应再次出现 approval_required（前端可再次审批）→ 再 reject（message 写"不要再调用"）→ 收到正常文字答复，工具未执行。
6. generate_report：走完 9 节点管线 → pipeline_step_frame 帧（node_update，node=各步骤名）顺序到达，无 generate_report 工具级 running/done 帧（抑制生效），done 帧 html_report 非空、report_updated=true。
7. export_report → done 帧 export_artifact.download_url 可下载。
8. 取消：长任务中 POST /cancel → cancelled 帧，后续帧停止。
9. 断线重连：任务进行中断网 → GET /runs/{tid} 查状态 → GET /runs/{tid}/stream?after=N 续接，帧游标连续。
10. 同会话多轮：第 2 轮引用第 1 轮上下文（"刚才查的活动"），确认会话状态连续。
11. 已知取舍确认：刷新页面后历史消息不恢复（P1 接受，P2 修复）——在验收文档明确记录此行为。
12. 回归对照：`AGENT_V3_ENABLED` 置 false 重启，跑一遍 1/3/6 确认 v2 路径不受影响。

- [ ] **Step 3: 写验收文档并 Commit**

`docs/superpowers/specs/2026-08-07-agent-v3-p1-acceptance.md`：上述 12 项逐项结果 + 发现的问题清单（未过项标注是否阻塞 P2）。

```bash
git add docs/superpowers/specs/2026-08-07-agent-v3-p1-acceptance.md
git commit -m "docs(agent_v3): P1 实机联调验收记录"
```

---

## Self-Review 记录

- **规格覆盖**：调研文档 §4 P1 五项（agent_v3 并行包 ✓ Task 2-9；工具 @tool 壳 ✓ Task 3-4；ApprovalEditRail ✓ Task 5；sse_bridge 重写 ✓ Task 8；_BufferedRun/取消/审计平移 ✓ Task 9；AGENT_V3_ENABLED 开关 ✓ Task 10）+ P0 回写三点（max_iterations ✓ Task 7；二次审批循环 ✓ Task 5/9/11；SSE 帧映射表 ✓ Task 8）+ t4 两项（工具上限 Rail ✓ Task 6；writer 桥接 ✓ Task 7）。P2 持久化、P3 管线、P4 离线包不在本计划。
- **已知刻意偏离 v2 之处**：v3 不发 token 级正文增量帧（v2 也不发，final_response 走 done 帧，契约一致）；`plan`/`report_html_guard_result` 在 done 帧的缺失与 v2 现状一致（前端有容错）。

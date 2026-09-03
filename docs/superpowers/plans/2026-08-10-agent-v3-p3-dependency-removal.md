# agent_v3 P3 实施计划：依赖摘除与 v2 退役

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 彻底摘除 langgraph/langchain/deepagents 依赖，agent_v3 成为唯一运行时，LLM 层迁到 openjiuwen Model。

**Architecture:** 工具实现层中立化（`agent_v3/tools/impl/`，ToolContext/ToolOutcome 契约）→ LLM 层新建 `src/llm.py`（get_model/GuardedModel）→ 管线节点 async 化 → 删 agent_v2 包与 `AGENT_V3_ENABLED` 开关 → requirements 删 8 条依赖。设计文档：`docs/superpowers/specs/2026-08-10-agent-v3-p3-dependency-removal-design.md`。

**Tech Stack:** openjiuwen 0.1.16.post2（Model/ModelClientConfig/ModelRequestConfig）、FastAPI、SQLAlchemy、pytest（无 pytest-asyncio，协程测试用 conftest 钩子 asyncio.run 执行，见 tests/agent_v3/conftest.py）。

## Global Constraints

- 工作目录一律 `backend/`；测试命令 `venv/bin/python -m pytest tests -q`（基线：300 passed + 2 个 M3 既有失败 test_tools_report_export，非回归）。
- 前端契约不动：HTTP 前缀 `/api/v2/agent/*` 保留；SSE 帧契约不变。
- 失败约定不变：工具失败返回 `"ERROR: <原因>"` 文本，不抛异常。
- 节点失败约定不变：返回 `{"next_agent": "finalize", "final_response": "<原因>"}` → PipelineAbort。
- `ModelContextLengthExceeded` / `MODEL_BUSY_MESSAGE` 异常与文案类型不变（`src/utils/token_budget.py` 是框架无关的，整体保留）。
- 每完成任务按给定消息 commit；不超前做后面任务的内容。
- openjiuwen import 副作用：load_dotenv(override=True) 会把 cwd 的 .env 写进 os.environ——测试须 delenv 或 monkeypatch 保证密封（见 tests/agent_v3/test_v3_config.py 模式）。

---

### Task 1: get_model spike——openjiuwen Model 对行内端点实测

**Files:**
- Create: `spikes/p3-model-spike/run_spike.py`

**Interfaces:**
- Produces: spike 结论（人工读输出确认 5 项全过），决定 Task 2 的 `GuardedModel` 参数映射；若关键项失败 → 停止并回报（回退路径：保留 langchain-openai，见设计 §5）。

- [ ] **Step 1: 写 spike 脚本**

```python
"""P3 spike：openjiuwen Model 对行内 deepseek 端点行为实测。

运行：cd spikes/p3-model-spike && ../../backend/venv/bin/python run_spike.py
（复用 backend/.env 的 LLM_* 配置；openjiuwen import 会 load_dotenv 自动加载）

验收 5 项：
1. 普通 invoke 返回 AssistantMessage，.content 非空；
2. max_tokens=16 时长输出被截断（usage 或 finish_reason 可见）；
3. timeout=0.001 时调用在 ~1s 内以超时类异常失败（记录异常类型全名）；
4. 5 并发 invoke 全部成功；
5. 错误调用（坏 api_key）失败并打印异常类型全名（供 is_timeout_exception/
   is_provider_context_limit_error 扩充参考）。
"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from openjiuwen.core.foundation.llm import ModelClientConfig, ModelRequestConfig, Model


def _make_model(**client_overrides) -> Model:
    client_cfg = ModelClientConfig(
        client_provider="OpenAI",
        api_key=os.environ.get("AGENT_V2_MAIN_LLM_API_KEY") or os.environ["LLM_API_KEY"],
        api_base=os.environ.get("AGENT_V2_MAIN_LLM_BASE_URL") or os.environ["LLM_BASE_URL"],
        timeout=client_overrides.pop("timeout", 120),
        **client_overrides,
    )
    request_cfg = ModelRequestConfig(
        model_name=os.environ.get("AGENT_V2_MAIN_LLM_MODEL") or os.environ["LLM_MODEL"],
        temperature=0.1,
    )
    return Model(client_cfg, request_cfg)


async def main() -> None:
    results = {}

    # 1. 普通调用
    r = await _make_model().invoke("用一句话回答：1+1等于几？")
    results["1_basic"] = bool(r.content and r.content.strip())
    print("1_basic content:", (r.content or "")[:80])
    print("1_basic usage_metadata:", getattr(r, "usage_metadata", None))
    print("1_basic finish_reason:", getattr(r, "finish_reason", None))

    # 2. max_tokens 截断
    r2 = await _make_model().invoke("写一篇 500 字关于春天的散文", max_tokens=16)
    print("2_max_tokens content_len:", len(r2.content or ""),
          "finish_reason:", getattr(r2, "finish_reason", None))
    results["2_max_tokens"] = len(r2.content or "") < 200

    # 3. 超时
    t0 = time.monotonic()
    try:
        await _make_model(timeout=0.001).invoke("你好")
        results["3_timeout"] = False
        print("3_timeout: 未超时（异常！）")
    except Exception as exc:
        elapsed = time.monotonic() - t0
        results["3_timeout"] = elapsed < 5
        print(f"3_timeout: {elapsed:.2f}s 抛出 {type(exc).__module__}.{type(exc).__name__}: {str(exc)[:120]}")

    # 4. 并发
    async def _call(i):
        return (await _make_model().invoke(f"只回答数字 {i}")).content
    outs = await asyncio.gather(*(_call(i) for i in range(5)))
    results["4_concurrent"] = all(bool(o) for o in outs)
    print("4_concurrent:", [str(o)[:10] for o in outs])

    # 5. 坏 api_key 错误类型
    try:
        await _make_model().client  # noqa
    except Exception:
        pass
    bad = Model(ModelClientConfig(
        client_provider="OpenAI", api_key="sk-bad", api_base=os.environ["LLM_BASE_URL"], timeout=30,
    ), ModelRequestConfig(model_name=os.environ["LLM_MODEL"], temperature=0.1))
    try:
        await bad.invoke("你好")
        results["5_auth_error"] = False
        print("5_auth_error: 未抛错（异常！）")
    except Exception as exc:
        results["5_auth_error"] = True
        print(f"5_auth_error: {type(exc).__module__}.{type(exc).__name__}: {str(exc)[:120]}")

    print("\n== 汇总 ==")
    for k, v in results.items():
        print(("PASS" if v else "FAIL"), k)
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
```

注意：`.env` 里 LLM_API_KEY/LLM_BASE_URL/LLM_MODEL 的实际键名以 backend/src/config.py 的 Settings 别名为准，写脚本前先 `grep -n 'alias="LLM_' backend/src/config.py` 核对。

- [ ] **Step 2: 运行 spike 并记录结果**

Run: `cd spikes/p3-model-spike && ../../backend/venv/bin/python run_spike.py`
Expected: 5 项全 PASS；把第 3/5 项的异常类型全名贴进 commit message 或 findings（供 Task 2 扩充异常判定）。

- [ ] **Step 3: Commit**

```bash
git add spikes/p3-model-spike/
git commit -m "test(agent_v3): P3 get_model spike——openjiuwen Model 端点行为实测"
```

---

### Task 2: `src/llm.py`——get_model 工厂 + GuardedModel

**Files:**
- Create: `backend/src/llm.py`
- Test: `backend/tests/test_llm_factory.py`（新建）
- Delete（在 Task 11 才物理删除，本任务停用）: `backend/src/utils/llm_logging.py` 的回调挂载点

**Interfaces:**
- Consumes: `src/utils/token_budget.py`（`estimate_model_request_tokens`/`ModelContextLengthExceeded`/`is_provider_context_limit_error`，框架无关，原样保留）;settings 的 `{role}_llm_*` 字段（config.py 既有，不动）。
- Produces:
  - `get_model(role: str = "report_generation", temperature: float = 0.1, use_cache: bool = True) -> GuardedModel`（角色配置语义与旧 get_llm 完全一致：`{role}_llm_api_key/base_url/model/max_tokens` 缺省回退全局 `llm_*`）
  - `GuardedModel.invoke(messages: str | list, **kwargs) -> AssistantMessage`（async；budget 守卫 + io 日志 + token 用量落库）
  - `reset_model_cache() -> None`（测试用）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_llm_factory.py`（协程测试需 conftest 钩子——把 tests/agent_v3/conftest.py 的 pytest_pyfunc_call 复制到 tests/conftest.py 并改为全局生效；若已存在全局钩子则跳过）:

```python
"""src/llm.py get_model/GuardedModel 离线测试（monkeypatch openjiuwen Model，不打真实端点）。"""
from types import SimpleNamespace

import src.llm as llm_mod
from src.utils.token_budget import ModelContextLengthExceeded


def _fake_settings(monkeypatch):
    s = SimpleNamespace(
        llm_api_key="k", llm_base_url="http://x", llm_model="m",
        llm_max_tokens=1000, llm_output_token_reserve=100,
        llm_timeout_seconds=600,
        report_generation_llm_api_key="", report_generation_llm_base_url="",
        report_generation_llm_model="", report_generation_llm_max_tokens=0,
    )
    monkeypatch.setattr(llm_mod, "get_settings", lambda: s)
    return s


def test_get_model_role_fallback_and_cache(monkeypatch):
    _fake_settings(monkeypatch)
    monkeypatch.setattr(llm_mod, "Model", lambda *a, **k: SimpleNamespace(invoke=None))
    llm_mod.reset_model_cache()
    m1 = llm_mod.get_model("report_generation")
    m2 = llm_mod.get_model("report_generation")
    assert m1 is m2  # 缓存
    assert m1._model_name == "m"  # 角色缺省回退全局


async def test_guarded_model_budget_guard(monkeypatch):
    _fake_settings(monkeypatch)
    monkeypatch.setattr(llm_mod, "Model", lambda *a, **k: SimpleNamespace(invoke=None))
    llm_mod.reset_model_cache()
    m = llm_mod.get_model("report_generation")
    try:
        await m.invoke("很" * 5000)  # 估算输入远超 limit=1000
        assert False, "应抛 ModelContextLengthExceeded"
    except ModelContextLengthExceeded:
        pass


async def test_guarded_model_invoke_logs_and_persists(monkeypatch, tmp_path):
    _fake_settings(monkeypatch)
    calls = {}

    class FakeModel:
        def __init__(self, *a, **k): pass
        async def invoke(self, messages, **kw):
            calls["messages"] = messages
            return SimpleNamespace(content="回答", usage_metadata={"total_tokens": 42})

    monkeypatch.setattr(llm_mod, "Model", FakeModel)
    # 用量落库走 SessionLocal——monkeypatch 为记录型假 session
    persisted = []
    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def add(self, row): persisted.append(row)
        def commit(self): pass
    monkeypatch.setattr(llm_mod, "SessionLocal", lambda: FakeSession())
    llm_mod.reset_model_cache()
    m = llm_mod.get_model("report_generation")
    r = await m.invoke("你好")
    assert r.content == "回答"
    assert persisted and persisted[0].token_cost == 42 and persisted[0].exec_status == "SUCCESS"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `venv/bin/python -m pytest tests/test_llm_factory.py -q`
Expected: FAIL（ModuleNotFoundError: src.llm）

- [ ] **Step 3: 实现 src/llm.py**

```python
"""LLM 访问层（openjiuwen Model）：角色化工厂 + 上下文预算守卫 + io 日志/用量落库。

替代原 config.get_llm（langchain ChatOpenAI）。角色配置语义与旧 get_llm 一致：
settings.{role}_llm_api_key/base_url/model/max_tokens，缺省回退全局 llm_*。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from openjiuwen.core.foundation.llm import Model, ModelClientConfig, ModelRequestConfig

from src.config import get_settings
from src.infrastructure.db.session import SessionLocal
from src.utils.token_budget import (
    ModelContextLengthExceeded,
    estimate_model_request_tokens,
    is_provider_context_limit_error,
)

logger = logging.getLogger("activity-analysis.agent")

_model_cache: dict[str, "GuardedModel"] = {}


def reset_model_cache() -> None:
    _model_cache.clear()


class GuardedModel:
    """openjiuwen Model 的薄 wrapper：预算守卫 + io 日志 + 用量落库（行为对齐旧 TokenBudgetChatOpenAI+LLMIOCharLogger）。"""

    def __init__(self, model: Model, *, model_name: str, context_limit: int,
                 output_reserve: int, label: str) -> None:
        self._model = model
        self._model_name = model_name
        # 避免统一预留值吃满小上下文模型（对齐旧 configure_token_budget 语义）
        max_default_reserve = max(context_limit // 4, 1)
        self._output_reserve = max(min(int(output_reserve), max_default_reserve), 0)
        self._context_limit = max(int(context_limit), 1)
        self._label = label

    async def invoke(self, messages, **kwargs):
        run_id = uuid4().hex
        msg_list = messages if isinstance(messages, list) else [messages]
        estimated = estimate_model_request_tokens(msg_list, kwargs)
        output_reserve = max(self._output_reserve, int(kwargs.get("max_tokens") or 0))
        logger.info("[LLM] Token预算 model=%s estimated_input=%d output_reserve=%d max_tokens=%d",
                    self._model_name, estimated, output_reserve, self._context_limit)
        if estimated + output_reserve > self._context_limit:
            logger.warning("[LLM] 请求超过模型上下文，已阻止调用: model=%s estimated_input=%d", self._model_name, estimated)
            raise ModelContextLengthExceeded(
                model=self._model_name, estimated_input=estimated,
                output_reserve=output_reserve, limit=self._context_limit)
        started_at = datetime.now(timezone.utc).replace(tzinfo=None)
        t0 = time.perf_counter()
        logger.info("[LLM] 请求 %s run=%s", self._label, run_id[:8])
        try:
            response = await self._model.invoke(messages, **kwargs)
        except Exception as exc:
            self._persist_usage(run_id, started_at, t0, 0, "FAILED")
            if is_provider_context_limit_error(exc):
                raise ModelContextLengthExceeded(
                    model=self._model_name, estimated_input=estimated,
                    output_reserve=output_reserve, limit=self._context_limit) from exc
            raise
        usage = getattr(response, "usage_metadata", None) or {}
        token_cost = int(usage.get("total_tokens") or 0) if isinstance(usage, dict) else int(getattr(usage, "total_tokens", 0) or 0)
        logger.info("[LLM] 返回 %s run=%s 输出字符=%d Token=%d",
                    self._label, run_id[:8], len(getattr(response, "content", "") or ""), token_cost)
        self._persist_usage(run_id, started_at, t0, token_cost, "SUCCESS")
        return response

    def _persist_usage(self, run_id: str, started_at, t0: float, token_cost: int, status: str) -> None:
        try:
            from src.infrastructure.db.models import LlmTokenUsageLog

            with SessionLocal() as db:
                db.add(LlmTokenUsageLog(
                    etl_dt=started_at.date(), id=run_id, start_time=started_at,
                    time_spent=max(round((time.perf_counter() - t0) * 1000), 0),
                    token_cost=max(int(token_cost or 0), 0), exec_status=status,
                ))
                db.commit()
        except Exception:
            logger.exception("[LLM] 调用统计写入失败 run=%s", run_id[:8])


def get_model(role: str = "report_generation", temperature: float = 0.1,
              use_cache: bool = True) -> GuardedModel:
    settings = get_settings()
    api_key = getattr(settings, f"{role}_llm_api_key", "") or settings.llm_api_key
    base_url = getattr(settings, f"{role}_llm_base_url", "") or settings.llm_base_url
    model = getattr(settings, f"{role}_llm_model", "") or settings.llm_model
    role_model = getattr(settings, f"{role}_llm_model", "")
    context_limit = int(getattr(settings, f"{role}_llm_max_tokens", 0) or settings.llm_max_tokens) if role_model else int(settings.llm_max_tokens)

    cache_key = f"{role}:{temperature}"
    if use_cache and cache_key in _model_cache:
        return _model_cache[cache_key]

    client_cfg = ModelClientConfig(
        client_provider="OpenAI", api_key=api_key, api_base=base_url,
        timeout=settings.llm_timeout_seconds,
    )
    request_cfg = ModelRequestConfig(model_name=model, temperature=temperature)
    guarded = GuardedModel(
        Model(client_cfg, request_cfg),
        model_name=model, context_limit=context_limit,
        output_reserve=settings.llm_output_token_reserve,
        label=f"{role}/{model}",
    )
    if use_cache:
        _model_cache[cache_key] = guarded
    return guarded
```

注意：`Model` 构造函数引用 `Runner.callback_framework`——离线测试中 monkeypatch `llm_mod.Model` 规避；真实运行时 Runner 已 start。若 spike（Task 1）发现无 Runner.start 时 Model 构造报错，在 get_model 里 try/except 记录即可（生产路径必有 Runner）。

- [ ] **Step 4: 跑测试确认通过**

Run: `venv/bin/python -m pytest tests/test_llm_factory.py -q`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/llm.py backend/tests/test_llm_factory.py backend/tests/conftest.py
git commit -m "feat(agent_v3): P3 src/llm.py——get_model 工厂 + GuardedModel（预算守卫/io日志/用量落库）"
```

---

### Task 3: 管线节点 async 化 + 接入 get_model

**Files:**
- Modify: `backend/src/report_pipeline/capabilities/template_matching.py`、`component_value_fetch.py`、`activity_template_matching.py`、`marketing_report_synthesis.py`（4 个 LLM 节点）
- Modify: `backend/src/report_pipeline/capabilities/` 其余节点（`template_list_fetch.py`、`component_value_cleanup.py`、`branch_drilldown.py`、`outbound_activity_data_fetch.py`、`selected_activity_router.py`、`uploaded_component_value_extract.py`——签名 async 化，函数体不动）
- Modify: `backend/src/agent_v2/tools/report_gen.py:385-480`（`run_report_pipeline` 改 async；工具入口调用点改 asyncio.run 包装）
- Test: `backend/tests/agent_v2/test_generate_report_pipeline.py` 及相关节点测试（加 await 适配；conftest 全局钩子 Task 2 已就位）

**Interfaces:**
- Consumes: `src.llm.get_model`（Task 2）。
- Produces: `async def run_report_pipeline(seed: dict, writer) -> dict`（签名其余不变）;9 个节点函数全部 `async def xxx_node(state: dict) -> dict`。

- [ ] **Step 1: 改 4 个 LLM 节点（每个节点同一模式）**

以 template_matching.py 为例，before：

```python
    llm = get_llm("report_generation", temperature=0.1)
    response = llm.invoke(format_runtime_prompt(...))
    logger.debug("...: %s", response.content)
```

after：

```python
    model = get_model("report_generation", temperature=0.1)
    response = await model.invoke(format_runtime_prompt(...))
    logger.debug("...: %s", response.content)
```

同时：`from src.config import get_llm` → `from src.llm import get_model`；函数签名 `def template_matching_node(state)` → `async def template_matching_node(state)`。component_value_fetch / activity_template_matching / marketing_report_synthesis 同样处理（各 1 处 invoke；marketing_report_synthesis 若有重试循环内的多次 invoke，每处都加 await）。

- [ ] **Step 2: 其余 5 个节点签名 async 化**

`def xxx_node(state)` → `async def xxx_node(state)`，函数体不动（内部 sync DB/HTTP 保持同步调用——管线整体跑在 worker 线程事件循环里，见 Step 4）。

- [ ] **Step 3: run_report_pipeline 改 async**

report_gen.py 中：

```python
async def run_report_pipeline(seed: dict, writer=lambda _event: None) -> dict:
    ...
    def step(...)  →  async def step(name, fn):
        ...
        update = await fn(s)
        ...
```

`step("selected_activity_router", selected_activity_router_node)` 等全部调用点不变（fn 已是 async）。

- [ ] **Step 4: 工具入口调用点改 asyncio.run 包装**

report_gen.py generate_report 工具体内，before：

```python
        result = await asyncio.to_thread(run_report_pipeline, seed, writer)
```

after：

```python
        result = await asyncio.to_thread(lambda: asyncio.run(run_report_pipeline(seed, writer)))
```

（管线仍在 worker 线程跑，内部是独立事件循环；同步 DB/HTTP 不进主循环，LLM 调用在该循环内真异步——语义与改造前等价。）

- [ ] **Step 5: 测试适配与全量回归**

节点测试若直接调用节点函数，改为 `asyncio.run(node(state))` 或利用全局 conftest 钩子改 async 测试。

Run: `venv/bin/python -m pytest tests -q`
Expected: 300 passed + 2 个 M3 既有失败（不新增失败）

- [ ] **Step 6: Commit**

```bash
git add backend/src/report_pipeline backend/src/agent_v2/tools/report_gen.py backend/tests
git commit -m "refactor(report_pipeline): P3 节点 async 化并接入 get_model（openjiuwen Model）"
```

---

### Task 4: impl 层骨架——ToolContext/ToolOutcome + 中立 helper 平移

**Files:**
- Create: `backend/src/agent_v3/tools/impl/__init__.py`（ToolContext/ToolOutcome）
- Create: `backend/src/agent_v3/tools/impl/context.py`（ToolRequestContext）
- Create: `backend/src/agent_v3/tools/impl/common.py`（_common.py 平移，去 langchain）
- Create: `backend/src/agent_v3/request_context.py`（从 agent_v2/state/request_context.py 平移）
- Test: `backend/tests/agent_v3/test_v3_impl_contract.py`（新建）

**Interfaces:**
- Produces（后续任务全部依赖）：
  - `ToolRequestContext(BaseModel)`：`user_id/user_name/org_no/src_sys_no/channel/uploaded_file_path/thread_id/request_id/original_user_text: str = ""`（9 字段）
  - `ToolContext` dataclass：`state: dict`、`request: ToolRequestContext`、`tool_call_id: str = ""`、`write_stream: Callable[[dict], None]`
  - `ToolOutcome` dataclass：`content: str`、`state_updates: dict`
  - `common.py`：`activity_key/activity_name/compact_activity/ok_content/error_content/summarize/is_timeout_exception/is_context_length_exception`（与 v2 _common 同名同行为；`tool_command` 不平移——由 ToolOutcome 替代；`resolve_state/resolve_context` 不平移——壳层直接组装 ToolContext）
  - `src/agent_v3/request_context.py`：`set_request_context/get_request_context/reset_request_context`（与 v2 版同名同语义）

- [ ] **Step 1: 写失败测试**

`backend/tests/agent_v3/test_v3_impl_contract.py`：

```python
"""impl 层契约测试：ToolContext/ToolOutcome/common helper。"""
from src.agent_v3.tools.impl import ToolContext, ToolOutcome
from src.agent_v3.tools.impl.common import (
    activity_key, activity_name, error_content, is_timeout_exception, ok_content, summarize,
)
from src.agent_v3.tools.impl.context import ToolRequestContext


def test_tool_context_defaults():
    ctx = ToolContext(state={"x": 1}, request=ToolRequestContext(user_id="u1"))
    assert ctx.state == {"x": 1}
    assert ctx.request.user_id == "u1"
    assert ctx.tool_call_id == ""
    ctx.write_stream({"step": "s"})  # 默认 no-op 不抛错


def test_tool_outcome():
    o = ToolOutcome(content="ok", state_updates={"html_report": "<html/>"})
    assert o.content == "ok" and o.state_updates == {"html_report": "<html/>"}
    assert ToolOutcome(content="x").state_updates == {}


def test_common_helpers():
    assert activity_key({"act_no": "A1"}) == "A1"
    assert activity_name({"活动名称": "活动X"}) == "活动X"
    assert error_content("失败") == "ERROR: 失败"
    assert "1" in ok_content({"a": 1})
    assert summarize("abcdef", 3) == "abc…"
    assert is_timeout_exception(TimeoutError("read timeout"))


def test_request_context_var():
    from src.agent_v3.request_context import (
        get_request_context, reset_request_context, set_request_context,
    )
    token = set_request_context({"user_id": "u9", "thread_id": "t9"})
    assert get_request_context()["user_id"] == "u9"
    reset_request_context(token)
    assert get_request_context() == {}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `venv/bin/python -m pytest tests/agent_v3/test_v3_impl_contract.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现四个文件**

`impl/__init__.py`：

```python
"""agent_v3 工具实现层契约：ToolContext 入参 / ToolOutcome 返回。

impl 模块无任何框架依赖（无 langchain/openjiuwen import），
壳层（agent_v3/tools/__init__.py）负责组装 ToolContext 并落 ToolOutcome。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.agent_v3.tools.impl.context import ToolRequestContext


def _noop_stream(_event: dict) -> None:
    return None


@dataclass
class ToolContext:
    state: dict
    request: ToolRequestContext
    tool_call_id: str = ""
    write_stream: Callable[[dict], None] = _noop_stream


@dataclass
class ToolOutcome:
    content: str
    state_updates: dict = field(default_factory=dict)
```

`impl/context.py`：

```python
"""工具请求上下文（从 agent_v2 AgentV2Context 平移，并入 turn 级两键）。

user_id/org_no/channel/file_path 等敏感参数只走此通道（及
request_context.ContextVar 兜底），绝不由 LLM 从对话中生成。
"""
from __future__ import annotations

from pydantic import BaseModel


class ToolRequestContext(BaseModel):
    user_id: str = ""
    user_name: str = ""
    org_no: str = ""
    src_sys_no: str = ""
    channel: str = ""
    uploaded_file_path: str = ""
    thread_id: str = ""
    request_id: str = ""
    original_user_text: str = ""
```

`impl/common.py`：从 `agent_v2/tools/_common.py` 平移 `activity_key/activity_name/compact_activity/ok_content/error_content/summarize/is_timeout_exception/is_context_length_exception`（含 `_TIMEOUT_*` 常量），删掉 langchain import 与 `tool_command/resolve_state/resolve_context`。

`request_context.py`：从 `agent_v2/state/request_context.py` 原样平移（读源文件照抄，仅改模块 docstring）。

- [ ] **Step 4: 跑测试确认通过 + 全量无回归**

Run: `venv/bin/python -m pytest tests/agent_v3/test_v3_impl_contract.py -q && venv/bin/python -m pytest tests -q`
Expected: 新测试 4 passed；全量 300 passed + 2 既有失败

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_v3/tools/impl backend/src/agent_v3/request_context.py backend/tests/agent_v3/test_v3_impl_contract.py
git commit -m "feat(agent_v3): P3 impl 层骨架——ToolContext/ToolOutcome 契约与中立 helper"
```

---

### Task 5: 简单工具模块平移（template / skill / activity_query / analysis_queue / data_parse）

**Files:**
- Create: `backend/src/agent_v3/tools/impl/template.py`、`skill.py`、`activity_query.py`、`analysis_queue.py`、`data_parse.py`
- Test: 沿用既有测试（tests/agent_v2/test_tools_* 中纯业务用例——本任务只把被测 import 路径指向 impl；框架注入类用例 test_tool_runtime_injection 删除）

**Interfaces:**
- Consumes: Task 4 的 ToolContext/ToolOutcome/common。
- Produces: 5 个 impl 模块，每个导出与 v2 同名的 async 函数，签名为 `(…业务参数…, ctx: ToolContext) -> str | ToolOutcome`。

- [ ] **Step 1: 平移变换公式（逐模块套用）**

以 template.py 为例。before（v2）：

```python
@tool(args_schema=GetAvailableTemplatesArgs)
async def get_available_templates(template_type: str = "", keyword: str = "", runtime: ToolRuntime = None):
    """查询可用的分析报告模板（含模板包含的分析技能列表）。"""
    try:
        templates = await asyncio.to_thread(list_agent_activity_templates, template_type, keyword)
    ...
    return ok_content({"count": len(compacted), "templates": compacted})
```

after（impl）：

```python
async def get_available_templates(ctx: ToolContext, template_type: str = "", keyword: str = "") -> str:
    try:
        templates = await asyncio.to_thread(list_agent_activity_templates, template_type, keyword)
    ...
    return ok_content({"count": len(compacted), "templates": compacted})
```

变换规则：
1. 删 `@tool(args_schema=...)` 装饰器与 args_schema 类（参数 schema 在 Task 8 的壳层用 openjiuwen @tool 的参数签名表达，描述文字从 docstring/Field description 平移到壳层）；
2. `runtime: ToolRuntime = None` → `ctx: ToolContext`（提到第一个位置参数）；
3. `resolve_state(runtime)` → `ctx.state`；`resolve_context(runtime)` → `ctx.request`（属性访问不变，字段名一致）；
4. `tool_command(content, runtime.tool_call_id, {...})` → `ToolOutcome(content, {...})`；
5. `from src.agent_v2.tools._common import ...` → `from src.agent_v3.tools.impl.common import ...`；
6. docstring 保留在壳层；impl 函数可留一行简述。

- [ ] **Step 2: 逐模块平移并适配测试 import**

5 个模块逐一应用 Step 1。测试中直接调用工具函数的（如 test_tools_analysis_queue），把调用改为组装 ToolContext：

```python
from src.agent_v3.tools.impl import ToolContext
from src.agent_v3.tools.impl.context import ToolRequestContext

def _ctx(state=None, **req):
    return ToolContext(state=state or {}, request=ToolRequestContext(**req))

# 调用：await impl_analysis_queue.add_to_analysis_queue(_ctx(...), activity_ids=["A1"])
```

- [ ] **Step 3: 全量回归**

Run: `venv/bin/python -m pytest tests -q`
Expected: 300 passed + 2 既有失败（v2 工具此时仍在，双份实现并存，测试两边都过）

- [ ] **Step 4: Commit**

```bash
git add backend/src/agent_v3/tools/impl backend/tests
git commit -m "feat(agent_v3): P3 简单工具 impl 平移（template/skill/activity_query/analysis_queue/data_parse）"
```

---

### Task 6: report_gen 平移（管线编排 + writer 显式注入）

**Files:**
- Create: `backend/src/agent_v3/tools/impl/report_gen.py`
- Test: `backend/tests/agent_v2/test_generate_report_pipeline.py`（import 指向 impl；Task 10 迁移文件名）

**Interfaces:**
- Consumes: Task 3 的 async 管线、Task 4 契约。
- Produces: `async def generate_report(ctx: ToolContext, activity_ids=None, data_source="analysis_queue", metrics=None, dimensions=None, perspective=None, chart_style=None, report_theme="", analysis_focus="", confirm_mixed=False) -> str | ToolOutcome`；`build_report_seed`/`run_report_pipeline` 随模块平移（run_report_pipeline 留在 impl/report_gen.py，与 v2 位置对应）。

- [ ] **Step 1: 平移 report_gen.py，应用 Task 5 变换公式 + 两处特殊处理**

特殊处理 1——writer 注入。before：

```python
from langgraph.config import get_stream_writer
...
    writer = get_stream_writer()
```

after：

```python
    writer = ctx.write_stream
```

（`patch_report_gen_writer` 在 Task 10 随 agent_factory 清理删除。）

特殊处理 2——seed 里的 langchain 消息。before：

```python
from langchain_core.messages import HumanMessage
...
        "messages": [HumanMessage(content=instruction)],
```

after：

```python
        "messages": [{"role": "user", "content": instruction}],
```

（`agent_run_history_service._original_user_text` 对 dict 消息按 role/type ∈ {"human","user"} 解析，语义一致——Task 11 还会摘掉它对 BaseMessage 的依赖。）

- [ ] **Step 2: 测试适配 + 全量回归**

Run: `venv/bin/python -m pytest tests -q`
Expected: 300 passed + 2 既有失败

- [ ] **Step 3: Commit**

```bash
git add backend/src/agent_v3/tools/impl/report_gen.py backend/tests
git commit -m "feat(agent_v3): P3 report_gen impl 平移——writer 显式注入，seed 去 langchain 消息"
```

---

### Task 7: report_modify + report_export 平移

**Files:**
- Create: `backend/src/agent_v3/tools/impl/report_modify.py`、`report_export.py`
- Test: `backend/tests/test_tools_report_export*.py`（2 个 M3 既有失败保持失败签名不变，不趁机修）

**Interfaces:**
- Produces: `async def modify_report(ctx, content_changes=None, chart_replacements=None, style_changes=None, free_instruction="") -> str | ToolOutcome`；`async def export_report(ctx, format="html", output_filename="") -> str | ToolOutcome`。

- [ ] **Step 1: 平移 report_modify，LLM 调用点改造**

除 Task 5 公式外，LLM 调用（2 处）。before：

```python
    llm = get_llm("report_generation", temperature=0.2)
    ...
        response = await asyncio.to_thread(llm.invoke, prompt)
```

after：

```python
    from src.llm import get_model
    model = get_model("report_generation", temperature=0.2)
    ...
        response = await model.invoke(prompt)
```

（工具本身已在 async 上下文，直接 await；不再要 to_thread。）

- [ ] **Step 2: 平移 report_export（无 LLM，纯 Task 5 公式）**

- [ ] **Step 3: 全量回归**

Run: `venv/bin/python -m pytest tests -q`
Expected: 300 passed + 2 既有失败（失败签名不变）

- [ ] **Step 4: Commit**

```bash
git add backend/src/agent_v3/tools/impl backend/tests
git commit -m "feat(agent_v3): P3 report_modify/report_export impl 平移，LLM 调用切 get_model"
```

---

### Task 8: v3 壳重写——直组 ToolContext，删 invoke_v2_tool

**Files:**
- Modify: `backend/src/agent_v3/tools/__init__.py`（整体重写）
- Test: `backend/tests/agent_v3/test_v3_tool_adapter.py`（重写为壳层契约测试）

**Interfaces:**
- Consumes: Task 4-7 的全部 impl。
- Produces: 13 个 openjiuwen `@tool` 壳（函数名/参数/docstring 与现状逐字一致——LLM 可见契约不动）；壳内统一模式：

```python
@tool
async def search_activities(keyword: str = "", ...) -> str:
    """<docstring 保持现状逐字不变>"""
    return await _run(impl_activity_query.search_activities, dict(keyword=keyword, ...))
```

其中 `_run` 为本模块私有 helper：

```python
async def _run(impl_fn, args: dict) -> str:
    """组装 ToolContext → 调 impl → ToolOutcome.state_updates 写会话。"""
    try:
        session = get_current_session()
    except Exception:
        session = None
    state = _state_snapshot(session) if session is not None else {}
    req = ToolRequestContext(**{k: v for k, v in get_request_context().items()
                                if k in ToolRequestContext.model_fields})
    ctx = ToolContext(state=state, request=req,
                      write_stream=_make_stream_writer(session))
    result = await impl_fn(ctx, **args)
    if isinstance(result, ToolOutcome):
        if result.state_updates and session is not None:
            session.update_state(result.state_updates)
        return result.content
    return result
```

`_make_stream_writer(session)`：返回闭包 `lambda event: asyncio.run_coroutine_threadsafe(session.write_custom_stream(dict(event)), loop)`（loop 在壳函数 async 上下文取 `asyncio.get_running_loop()`；session 为 None 时返回 no-op）。这正是现 `patch_report_gen_writer` 的逻辑，转正为壳层显式注入。

- [ ] **Step 1: 重写壳层测试**

test_v3_tool_adapter.py 重写：monkeypatch 一个 impl 函数，断言①业务参数透传；②ToolContext.state 含会话快照七键；③ToolOutcome.state_updates 写入 session（假 session 记录 update_state）；④str 返回直传。参考现有测试的 fake 模式（SimpleNamespace session）。

- [ ] **Step 2: 跑测试确认失败**

Run: `venv/bin/python -m pytest tests/agent_v3/test_v3_tool_adapter.py -q`
Expected: FAIL（_run 不存在）

- [ ] **Step 3: 重写 `agent_v3/tools/__init__.py`**

13 个壳逐一按上方模式改写（docstring 逐字保留！openjiuwen @tool 的 description 在 docstring 首个空行截断——保持单段无空行）。`invoke_v2_tool`/`_TURN_STATE_KEYS`/langgraph Command import 全部删除；`ALL_V3_TOOLS` 列表不变。

- [ ] **Step 4: 全量回归**

Run: `venv/bin/python -m pytest tests -q`
Expected: 300 passed + 2 既有失败

- [ ] **Step 5: Commit**

```bash
git add backend/src/agent_v3/tools/__init__.py backend/tests/agent_v3/test_v3_tool_adapter.py
git commit -m "refactor(agent_v3): P3 工具壳直组 ToolContext，删除 invoke_v2_tool 适配层"
```

---

### Task 9: prompts 迁移

**Files:**
- Create: `backend/src/agent_v3/prompts/__init__.py`、`system.py`、`perspectives.py`（从 agent_v2/prompts 平移）
- Modify: `backend/src/agent_v3/agent_factory.py`（`from src.agent_v2.prompts.system import build_system_prompt` → `from src.agent_v3.prompts.system import build_system_prompt`；同时删 `patch_report_gen_writer` 函数及其调用——Task 6 后它已是死代码）
- Modify: `backend/src/agent_v3/tools/impl/report_gen.py`（`from src.agent_v2.prompts.perspectives import ...` → `from src.agent_v3.prompts.perspectives import ...`）
- Test: `backend/tests/agent_v2/test_system_prompt.py` → 移到 `backend/tests/agent_v3/test_v3_system_prompt.py`，import 同步

- [ ] **Step 1: 平移文件并更新全部引用**

Run: `grep -rn "agent_v2.prompts" backend/src backend/tests` 逐一更新。

- [ ] **Step 2: 全量回归**

Run: `venv/bin/python -m pytest tests -q`
Expected: 300 passed + 2 既有失败

- [ ] **Step 3: Commit**

```bash
git add backend/src/agent_v3/prompts backend/src/agent_v3/agent_factory.py backend/src/agent_v3/tools/impl/report_gen.py backend/tests
git commit -m "refactor(agent_v3): P3 prompts 迁移到 agent_v3，删除 patch_report_gen_writer hack"
```

---

### Task 10: 删 agent_v2 包 + 开关摘除

**Files:**
- Delete: `backend/src/agent_v2/`（整个目录）
- Modify: `backend/src/api/routers/agent_v2.py`（去开关直挂 v3；文件改名 agent_chat.py 可选——若改名须同步 `src/api/routers/__init__.py`，URL 前缀 `/v2/agent` 不变）
- Modify: `backend/src/main.py`（lifespan 去 `agent_v3_enabled` 分支：init_v3_checkpointer/Runner.start 无条件执行；shutdown 同理；删 `close_agent` 调用）
- Modify: `backend/src/config.py`（删 `agent_v3_enabled` 字段；`agent_v3_max_iterations`/`agent_v3_checkpointer_db_path` 保留——改名是纯 churn 不改）
- Modify: `backend/src/api/routers/conversations.py`（删 `_get_checkpoint_saver` 及 DELETE 内 langgraph checkpoint 清理段）
- Delete: `backend/tests/agent_v2/` 中 v2 专属（hitl/sse_bridge/model_router/runtime_config/state_concurrent_writes/tool_runtime_injection 等）；纯业务用例已在 Task 5-7 指向 impl——本任务把残留文件物理移到 tests/agent_v3 或 tests/report_pipeline

**Interfaces:**
- Consumes: Task 4-9 的全部产出。
- Produces: v3 唯一运行时；`.env` 的 `AGENT_V3_ENABLED` 成为无效键（文档任务在 Task 12 说明）。

- [ ] **Step 1: routers 直挂 v3**

routers/agent_v2.py 每个端点删 `if get_settings().agent_v3_enabled:` 分支，保留 v3 路径。例如 run：

```python
@router.post("/run")
async def run(body: AgentRunRequest):
    kwargs = dict(thread_id=body.thread_id, message=body.message, ...)
    stream = await v3_runtime.start_buffered_agent_run(**kwargs)
    return StreamingResponse(stream, media_type="text/event-stream")
```

（顶部 import 从延迟改为直接 `from src.agent_v3 import runtime as v3_runtime`。）

- [ ] **Step 2: main.py / config.py / conversations.py 清理**

按 Files 清单逐项删改。conversations.py DELETE 只保留 v3 checkpoint 清理 + meta 删除。

- [ ] **Step 3: 删 agent_v2 包与 v2 专属测试，迁移残留业务测试**

```bash
git rm -r backend/src/agent_v2
# tests/agent_v2 逐个甄别：已在 Task 5-7 改指向 impl 的文件 git mv 到 tests/agent_v3/；v2 专属 git rm
```

- [ ] **Step 4: 全量回归 + import 扫描**

Run: `venv/bin/python -m pytest tests -q && grep -rn "agent_v2" backend/src --include="*.py" | grep -v "routers/agent_v2.py\|v2/agent"`
Expected: 测试全绿（总数随删減少）；grep 仅剩 URL 前缀/文件名类无害残留

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(agent_v3): P3 删除 agent_v2 包与 AGENT_V3_ENABLED 开关，v3 成为唯一运行时"
```

---

### Task 11: 收尾清零——去 langchain 最后残留 + requirements

**Files:**
- Modify: `backend/src/services/agent_run_history_service.py:14,1384,1402`（去 BaseMessage）
- Modify: `backend/src/report_pipeline/state.py:13-14,31`（去 add_messages/BaseMessage）
- Modify: `backend/src/config.py`（删 get_llm/_build_llm/TokenBudgetChatOpenAI/_llm_cache/ChatOpenAI import/LLMIOCharLogger import）
- Delete: `backend/src/utils/llm_logging.py`
- Modify: `backend/requirements.txt`、`requirements-offline.txt`（删 8 条）
- Modify: `backend/src/agent_v3/events/sse_bridge.py`（`from src.agent_v2.events.sse_bridge import ...`、`from src.agent_v2.tools import TOOL_DISPLAY_NAMES`、`from src.agent_v2.tools._common import activity_key, activity_name`——Task 10 后这些 import 已随包删除报错，须指向 impl/common 或平移到 v3）

**Interfaces:**
- Produces: `grep -rn "langchain\|langgraph\|deepagents" backend/src --include="*.py"` 结果为零。

- [ ] **Step 1: agent_run_history_service 去 BaseMessage**

1384/1402 处的 `isinstance(message, BaseMessage)` 改 duck-typing：

```python
# before
message_type = getattr(message, "type", "") if isinstance(message, BaseMessage) else ""
# after——消息对象已绝迹（v3 全是 dict），保留属性兜底即可
message_type = getattr(message, "type", "") if not isinstance(message, dict) else ""
```

（1402 同理：dict 走 dict 分支，其余按属性取 content。）删 `from langchain_core.messages import BaseMessage`。

- [ ] **Step 2: state.py 去 langchain**

```python
# before
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
...
    messages: Annotated[list[BaseMessage], add_messages]
# after（运行时本就是 plain dict 操作，标注仅为历史遗留）
    messages: list[dict]
```

（TypedDict 其余键不动；`Annotated` import 若无其他使用一并删。）

- [ ] **Step 3: config.py 删 LLM 旧栈 + 删 llm_logging.py**

删 `TokenBudgetChatOpenAI`/`_build_llm`/`get_llm`/`_llm_cache` 及相关 import（ChatOpenAI、PrivateAttr、LLMIOCharLogger、estimate_* 若仅用于此）。`git rm backend/src/utils/llm_logging.py`。`settings.llm_*` 字段保留（src/llm.py 在用）。

- [ ] **Step 4: sse_bridge import 修正**

v3 sse_bridge 引用的 `_compact_report_context/_export_artifact/_frame/pipeline_step_frame/tool_progress_frame`（来自 v2 sse_bridge）与 `TOOL_DISPLAY_NAMES`（v2 tools/__init__）、`activity_key/activity_name`（v2 _common）——把这些 helper 平移到 `src/agent_v3/events/_frames.py`（或 impl/common），import 指向新位置。注意保持函数体逐字不变（帧契约）。

- [ ] **Step 5: requirements 删 8 条 + 验证 import 清零**

requirements.txt 与 requirements-offline.txt 删除：langgraph、langchain、langchain-core、langchain-openai、langgraph-checkpoint-sqlite、deepagents、langchain-anthropic、langchain-google-genai。

Run: `grep -rn "langchain\|langgraph\|deepagents" backend/src --include="*.py" ; venv/bin/python -m pytest tests -q`
Expected: grep 零输出；测试全绿（2 既有失败除外）。注意 venv 里仍装着这些包——import 清零靠 grep 保证；卸载验证在 Task 12 新环境做。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore(agent_v3): P3 清零 langchain/langgraph 残留，requirements 删 8 条依赖"
```

---

### Task 12: 实机联调回归（人工验收）

**Files:**
- Create: `docs/superpowers/specs/2026-08-10-agent-v3-p3-acceptance.md`（验收后填写）

- [ ] **Step 1: 起服务全链路回归**

`AGENT_V3_ENABLED` 已从 .env 删除（无效键）。起 backend + 前端，按 P1/P2 清单回归，重点：
1. 纯问答；2. 查询工具；3. 审批 approve/edit/reject（含二次审批）；4. generate_report 全流程（进度帧逐步骤到达——验证 writer 显式注入替代 patch 后无回归）；5. modify_report（LLM 调用走 GuardedModel）；6. export_report；7. 取消；8. 断线重连；9. 重启续聊 + 刷新恢复（P2 清单）；10. `[LLM]` 日志与 llm_token_usage_log 表有新记录（GuardedModel 落库）。

- [ ] **Step 2: 干净环境 import 验证（可选但推荐）**

新建干净 venv 只装删减后的 requirements，`python -c "import src.main"` 通过。

- [ ] **Step 3: 写验收记录并 Commit**

```bash
git add docs/superpowers/specs/2026-08-10-agent-v3-p3-acceptance.md
git commit -m "docs(agent_v3): P3 实机联调验收记录"
```

---

## Self-Review 记录

- **Spec 覆盖**：设计 §4.1→Task 4-8；§4.2→Task 2-3、7；§4.3 删除清单→Task 9-11；§5 风险 spike→Task 1；§6 测试→各任务内 + Task 12。无缺口。
- **类型一致性**：`ToolContext/ToolOutcome/ToolRequestContext/get_model/GuardedModel/reset_model_cache/run_report_pipeline` 在 Produces 与 Consumes 间逐字一致。
- **顺序依赖**：1→2→3→4→5,6,7→8→9→10→11→12；Task 3 与 Task 6 的交错（管线 async 化先于 report_gen 平移）已在 Task 3 Step 4 处理中间态。

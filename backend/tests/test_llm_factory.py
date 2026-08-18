"""src/llm.py get_model/GuardedModel 离线测试（monkeypatch openjiuwen Model，不打真实端点）。"""
from types import SimpleNamespace

import src.llm as llm_mod
from src.utils.token_budget import ModelContextLengthExceeded


def _fake_settings(monkeypatch):
    s = SimpleNamespace(
        llm_api_key="k", llm_base_url="http://x", llm_model="m",
        llm_max_tokens=1000, llm_output_token_reserve=100,
        llm_timeout_seconds=600,
        llm_verify_ssl=False,
        report_generation_llm_api_key="", report_generation_llm_base_url="",
        report_generation_llm_model="", report_generation_llm_max_tokens=0,
    )
    monkeypatch.setattr(llm_mod, "get_settings", lambda: s)
    return s


def _fake_session(monkeypatch):
    """用量落库走 SessionLocal——monkeypatch 为记录型假 session。"""
    persisted = []

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def add(self, row): persisted.append(row)
        def commit(self): pass

    monkeypatch.setattr(llm_mod, "SessionLocal", lambda: FakeSession())
    return persisted


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
    persisted = _fake_session(monkeypatch)
    llm_mod.reset_model_cache()
    m = llm_mod.get_model("report_generation")
    r = await m.invoke("你好")
    assert r.content == "回答"
    assert persisted and persisted[0].token_cost == 42 and persisted[0].exec_status == "SUCCESS"


async def test_guarded_model_usage_metadata_object_form(monkeypatch):
    """openjiuwen 真实响应的 usage_metadata 是对象（非 dict），token_cost 须兼容两种形态。"""
    _fake_settings(monkeypatch)

    class FakeModel:
        def __init__(self, *a, **k): pass
        async def invoke(self, messages, **kw):
            return SimpleNamespace(
                content="ok",
                usage_metadata=SimpleNamespace(total_tokens=7, input_tokens=5, output_tokens=2),
            )

    monkeypatch.setattr(llm_mod, "Model", FakeModel)
    persisted = _fake_session(monkeypatch)
    llm_mod.reset_model_cache()
    m = llm_mod.get_model("report_generation")
    await m.invoke("你好")
    assert persisted and persisted[0].token_cost == 7


async def test_guarded_model_timeout_kwarg_forwarded(monkeypatch):
    """共享客户端缓存键不含 timeout——逐请求超时必须经 invoke(..., timeout=...) 透传。"""
    _fake_settings(monkeypatch)
    seen = {}

    class FakeModel:
        def __init__(self, *a, **k): pass
        async def invoke(self, messages, **kw):
            seen.update(kw)
            return SimpleNamespace(content="ok", usage_metadata={"total_tokens": 1})

    monkeypatch.setattr(llm_mod, "Model", FakeModel)
    _fake_session(monkeypatch)
    llm_mod.reset_model_cache()
    m = llm_mod.get_model("report_generation")
    await m.invoke("你好", timeout=0.5)
    assert seen.get("timeout") == 0.5


async def test_guarded_model_default_timeout_applied(monkeypatch):
    """未显式传 timeout 时，invoke 用实例配置超时（llm_timeout_seconds=600）做默认。"""
    _fake_settings(monkeypatch)
    seen = {}

    class FakeModel:
        def __init__(self, *a, **k): pass
        async def invoke(self, messages, **kw):
            seen.update(kw)
            return SimpleNamespace(content="ok", usage_metadata={"total_tokens": 1})

    monkeypatch.setattr(llm_mod, "Model", FakeModel)
    _fake_session(monkeypatch)
    llm_mod.reset_model_cache()
    m = llm_mod.get_model("report_generation")
    await m.invoke("你好")
    assert seen.get("timeout") == 600


async def test_guarded_model_explicit_timeout_overrides_default(monkeypatch):
    """显式传 timeout 时优先于实例默认（setdefault 语义）。"""
    _fake_settings(monkeypatch)
    seen = {}

    class FakeModel:
        def __init__(self, *a, **k): pass
        async def invoke(self, messages, **kw):
            seen.update(kw)
            return SimpleNamespace(content="ok", usage_metadata={"total_tokens": 1})

    monkeypatch.setattr(llm_mod, "Model", FakeModel)
    _fake_session(monkeypatch)
    llm_mod.reset_model_cache()
    m = llm_mod.get_model("report_generation")
    await m.invoke("你好", timeout=30)
    assert seen.get("timeout") == 30


async def test_guarded_model_context_error_via_cause_chain(monkeypatch):
    """openjiuwen 把底层异常包成 FrameworkError，原始异常在 __cause__——须沿链判定上下文超限。"""
    _fake_settings(monkeypatch)

    class FakeFrameworkError(Exception):
        pass

    class FakeModel:
        def __init__(self, *a, **k): pass
        async def invoke(self, messages, **kw):
            provider_exc = Exception("Error code: 400 - maximum context length exceeded")
            wrapper = FakeFrameworkError("[181001] model call failed")
            wrapper.__cause__ = provider_exc
            raise wrapper

    monkeypatch.setattr(llm_mod, "Model", FakeModel)
    persisted = _fake_session(monkeypatch)
    llm_mod.reset_model_cache()
    m = llm_mod.get_model("report_generation")
    try:
        await m.invoke("你好")
        assert False, "应沿 __cause__ 链识别上下文超限并抛 ModelContextLengthExceeded"
    except ModelContextLengthExceeded:
        pass
    assert persisted and persisted[0].exec_status == "FAILED"


async def test_guarded_model_non_context_error_reraises(monkeypatch):
    """非上下文类错误（含 __cause__ 链）原样上抛，不误判。"""
    _fake_settings(monkeypatch)

    class FakeFrameworkError(Exception):
        pass

    class FakeModel:
        def __init__(self, *a, **k): pass
        async def invoke(self, messages, **kw):
            wrapper = FakeFrameworkError("[181001] model call failed, reason: Request timed out.")
            wrapper.__cause__ = TimeoutError("Request timed out.")
            raise wrapper

    monkeypatch.setattr(llm_mod, "Model", FakeModel)
    persisted = _fake_session(monkeypatch)
    llm_mod.reset_model_cache()
    m = llm_mod.get_model("report_generation")
    try:
        await m.invoke("你好")
        assert False, "超时应原样上抛"
    except FakeFrameworkError:
        pass
    assert persisted and persisted[0].exec_status == "FAILED"

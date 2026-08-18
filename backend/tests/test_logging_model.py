"""LoggingModel 契约测试：框架（openjiuwen react_agent）在 invoke/stream 前会
无条件探测模型能力方法（supports_kv_cache_release / build_kv_cache_invoke_kwargs
等），LoggingModel 作为懒初始化包装必须保证这些探测不抛 AttributeError。

回归背景：LoggingModel 曾继承 openjiuwen Model 但不调 super().__init__()，
继承来的能力方法访问 self._client 时抛
"'LoggingModel' object has no attribute '_client'"，前台对话首轮即报错。
"""

from types import SimpleNamespace

from src.llm import LoggingModel


def _make_model() -> LoggingModel:
    return LoggingModel(
        SimpleNamespace(client_provider="OpenAI", api_key="k", api_base="http://x"),
        SimpleNamespace(model="m", temperature=0.1),
        label="test",
    )


def test_framework_capability_probes_do_not_raise():
    """框架调用前探测的能力方法要么不存在，要么可安全调用。"""
    m = _make_model()
    for name in (
        "supports_kv_cache_release",
        "supports_kv_cache_affinity",
        "build_kv_cache_invoke_kwargs",
        "build_kv_cache_affinity_invoke_kwargs",
    ):
        fn = getattr(m, name, None)
        if callable(fn):
            fn()  # 不得抛 AttributeError


def test_logging_model_exposes_only_duck_typed_interface():
    """日志包装只承诺 invoke/stream 两个入口，不冒充完整 Model。"""
    m = _make_model()
    assert callable(m.invoke)
    assert callable(m.stream)

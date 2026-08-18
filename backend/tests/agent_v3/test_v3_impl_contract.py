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


def test_is_timeout_exception_walks_cause_chain():
    """框架包装异常（如 openjiuwen FrameworkError）应从 __cause__ 链识别超时。"""
    class FrameworkError(Exception):
        """模拟 openjiuwen 框架包装异常，本身无超时特征。"""

    wrapped: BaseException
    try:
        try:
            raise TimeoutError()
        except TimeoutError as raw:
            raise FrameworkError("framework call failed") from raw
    except FrameworkError as exc:
        wrapped = exc
    assert "timeout" not in f"{type(wrapped).__module__}.{type(wrapped).__name__}".lower()
    assert "timeout" not in str(wrapped).lower()
    assert is_timeout_exception(wrapped)


def test_request_context_var():
    from src.agent_v3.request_context import (
        get_request_context, reset_request_context, set_request_context,
    )
    token = set_request_context({"user_id": "u9", "thread_id": "t9"})
    assert get_request_context()["user_id"] == "u9"
    reset_request_context(token)
    assert get_request_context() == {}

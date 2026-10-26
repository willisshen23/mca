"""插话/停止后旧管线尽快中止 + 脏报告版本不落库的回归测试。

背景：被取消的 run 其 stream_process 在后台续跑，整条报告管线会跑完——
多烧 LLM 调用，且每个后台 run 都把自己的报告版本（约 1MB blob）按各自
request_id 写入 report_versions，造成数据混乱。修复：cancel_event 经
request_context ContextVar 传入管线（stream_process 创建时拷贝上下文，
旧 run 只看到自己那一届的事件），阶段边界与存库双保险检查。
"""

import asyncio

import pytest

from src.agent_v3.request_context import (
    reset_request_context,
    set_request_context,
)
from src.report_pipeline.capabilities.utils import (
    RunCancelledError,
    raise_if_run_cancelled,
)


def test_no_cancel_event_is_noop():
    token = set_request_context({})
    try:
        raise_if_run_cancelled()  # 不抛即通过
    finally:
        reset_request_context(token)


def test_unset_cancel_event_is_noop():
    token = set_request_context({"cancel_event": asyncio.Event()})
    try:
        raise_if_run_cancelled()
    finally:
        reset_request_context(token)


def test_set_cancel_event_raises():
    event = asyncio.Event()
    event.set()
    token = set_request_context({"cancel_event": event})
    try:
        with pytest.raises(RunCancelledError) as exc_info:
            raise_if_run_cancelled()
        assert "请勿重试" in str(exc_info.value)
    finally:
        reset_request_context(token)


def test_save_report_file_skips_when_cancelled(monkeypatch):
    """取消的 run 存库直接跳过，不得写 report_versions。"""
    from src.services import agent_run_history_service as svc

    event = asyncio.Event()
    event.set()
    token = set_request_context({"cancel_event": event})
    try:
        # 若守卫失效会走到 DB 查询并抛异常——这里不给 DB 也能证明被跳过
        asset_name, version_no = svc.save_report_file("req-x", "<html>report</html>")
        assert (asset_name, version_no) == ("", None)
    finally:
        reset_request_context(token)


def test_cancel_event_scoped_to_own_run():
    """旧 run 的事件被置位不影响新一届（同名 thread）的上下文。"""
    old_event = asyncio.Event()
    old_event.set()
    new_event = asyncio.Event()
    token_old = set_request_context({"cancel_event": old_event})
    try:
        with pytest.raises(RunCancelledError):
            raise_if_run_cancelled()
        # 模拟新 run：在同一协程里换绑新事件（实际由 ContextVar 隔离）
        token_new = set_request_context({"cancel_event": new_event})
        try:
            raise_if_run_cancelled()  # 新 run 不抛
        finally:
            reset_request_context(token_new)
    finally:
        reset_request_context(token_old)

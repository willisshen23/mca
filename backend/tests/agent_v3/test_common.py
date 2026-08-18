"""agent_v3.tools.impl.common 共享辅助函数测试。"""
from __future__ import annotations

import pytest

from src.agent_v3.tools.impl.common import is_timeout_exception


class FakeTimeoutError(Exception):
    pass


class FakeReadTimeout(Exception):
    pass


class FakeAPITimeoutError(Exception):
    pass


def test_timeout_builtin_timeout_error():
    assert is_timeout_exception(TimeoutError("timed out")) is True


def test_timeout_asyncio_timeout_error():
    import asyncio

    assert is_timeout_exception(asyncio.TimeoutError()) is True


def test_timeout_by_type_name():
    assert is_timeout_exception(FakeReadTimeout("connection lost")) is True
    assert is_timeout_exception(FakeAPITimeoutError("server slow")) is True


def test_timeout_by_message():
    assert is_timeout_exception(RuntimeError("ReadTimeout: request timed out")) is True
    assert is_timeout_exception(ValueError("请求超时，请稍后重试")) is True
    assert is_timeout_exception(ConnectionError("Connection timed out after 30s")) is True


def test_non_timeout_exception():
    assert is_timeout_exception(ValueError("bad request")) is False
    assert is_timeout_exception(KeyError("missing")) is False
    assert is_timeout_exception(None) is False

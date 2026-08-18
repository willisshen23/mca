"""tests 全局共享 conftest。

backend venv 未安装 pytest-asyncio（离线环境不可新增依赖），而部分测试
（如 agent_v3 适配层、src/llm.py 工厂测试）为 `async def`。这里用 pytest
内置钩子把协程测试交给 asyncio.run 执行，全局生效；与仓库既有约定
（sync 测试 + asyncio.run）语义一致。

原 tests/agent_v3/conftest.py 的同名钩子已被本全局钩子覆盖，故删除以避免
重复执行。
"""

import asyncio
import inspect


def pytest_pyfunc_call(pyfuncitem):
    """协程测试函数用 asyncio.run 执行；返回 True 阻止默认（会失败的）调用。"""
    if inspect.iscoroutinefunction(pyfuncitem.function):
        kwargs = {
            name: pyfuncitem.funcargs[name]
            for name in pyfuncitem._fixtureinfo.argnames
        }
        asyncio.run(pyfuncitem.function(**kwargs))
        return True
    return None

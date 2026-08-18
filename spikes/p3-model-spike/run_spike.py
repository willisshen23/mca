"""P3 spike：openjiuwen Model 对行内 deepseek 端点行为实测。

运行：cd spikes/p3-model-spike && ../../backend/venv/bin/python run_spike.py
（复用 backend/.env 的 LLM_* 配置；脚本显式加载该文件——实测 openjiuwen
 import 并不会自动 load_dotenv，与任务书注释不同）

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


def _load_backend_env() -> None:
    """显式加载 backend/.env（键名以 backend/src/config.py 的 Settings 别名为准：
    LLM_API_KEY / LLM_BASE_URL / LLM_MODEL）。"""
    env_path = os.path.join(os.path.dirname(__file__), "../../backend/.env")
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_backend_env()

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
    # 注意：ModelClientConfig.timeout 在共享客户端路径下仅在首次建连时生效
    # （缓存键 = api_key/api_base/verify_ssl/ssl_cert，不含 timeout），
    # 因此必须用 invoke 级 timeout 参数才能真实触发超时。
    t0 = time.monotonic()
    try:
        await _make_model().invoke("你好", timeout=0.001)
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

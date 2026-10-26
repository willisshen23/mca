from __future__ import annotations

import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger("activity-analysis.agent")


_ECHARTS_LOCAL_SRC = "/lib/echarts.min.js"
_ECHARTS_SRC_PATTERN = re.compile(
    r'''https?://[^"'\s]*echarts[^"'\s]*\.min\.js|/[^"'\s]*echarts[^"'\s]*\.min\.js''',
    re.IGNORECASE,
)


def strip_code_fence(text: str) -> str:
    """Strip markdown code block fences like ```html and ```."""
    text = re.sub(r"^```\w*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    return text.strip()


def extract_html_content(text: str) -> str:
    """Extract only the HTML portion from LLM output, dropping explanatory text.

    Some models prepend phrases like "Here is the HTML code:" or wrap the
    output in markdown fences. This function keeps the first HTML tag onward
    and trims trailing non-HTML text.
    """
    text = strip_code_fence(text)
    start_match = re.search(r"<(html|!DOCTYPE|!doctype|section|div|body|head|main|article)", text, re.IGNORECASE)
    if not start_match:
        return text.strip()
    start = start_match.start()
    end = text.rfind("</html>")
    if end == -1:
        end = len(text)
    else:
        end += len("</html>")
    return text[start:end].strip()


def _is_bare_object_literal(content: str) -> bool:
    """Check if script content is a single bare JSON/object literal."""
    stripped = content.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return False
    # Verify it roughly parses as an object literal by checking brace balance.
    depth = 0
    in_string = False
    string_char = None
    escaped = False
    for i, ch in enumerate(stripped):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if in_string:
            if ch == string_char:
                in_string = False
            continue
        if ch in ('"', "'"):
            in_string = True
            string_char = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and i != len(stripped) - 1:
                # There is content after the closing brace of the outer object.
                return False
    return depth == 0 and not in_string


def _find_chart_container(script) -> str | None:
    """Find the nearest preceding chart container div for a script."""
    # Search siblings first.
    prev = script.find_previous_sibling()
    while prev:
        if prev.name == "div":
            div_id = prev.get("id") or ""
            if div_id.lower().startswith("chart"):
                return div_id
        prev = prev.find_previous_sibling()

    # Then search ancestors and their preceding siblings.
    parent = script.find_parent()
    while parent:
        prev = parent.find_previous_sibling()
        while prev:
            if prev.name == "div":
                div_id = prev.get("id") or ""
                if div_id.lower().startswith("chart"):
                    return div_id
            # Also search inside the sibling for chart divs.
            chart_div = prev.find("div", id=lambda x: x and x.lower().startswith("chart"))
            if chart_div:
                return chart_div.get("id")
            prev = prev.find_previous_sibling()
        parent = parent.find_parent()

    # Search anywhere before this script for a chart div.
    all_charts = [
        tag.get("id")
        for tag in script.find_all_previous("div")
        if (tag.get("id") or "").lower().startswith("chart")
    ]
    return all_charts[0] if all_charts else None


def fix_echarts_scripts(html: str) -> str:
    """Fix common LLM mistakes in ECharts HTML reports.

    1. Normalize all ECharts library references to the local path and ensure the
       library is loaded synchronously in <head> before any chart scripts.
    2. Wrap bare ECharts option object literals inside IIFE init code.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return html

    rewritten = False

    # 1. Normalize ECharts library references.
    echarts_scripts = []
    for script in soup.find_all("script"):
        src = script.get("src", "")
        if src and _ECHARTS_SRC_PATTERN.search(src):
            # Normalize to local path; remove async/defer so it loads synchronously.
            script["src"] = _ECHARTS_LOCAL_SRC
            if script.get("async") is not None:
                del script["async"]
            if script.get("defer") is not None:
                del script["defer"]
            if script.get("type") == "text/javascript":
                del script["type"]
            echarts_scripts.append(script)
            rewritten = True

    # Ensure exactly one ECharts script exists in <head>.
    head = soup.find("head")
    if head is None:
        head = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)

    if not echarts_scripts:
        echarts_script = soup.new_tag("script", src=_ECHARTS_LOCAL_SRC)
        head.append(echarts_script)
        rewritten = True
    else:
        # Move the first normalized script to the head and remove duplicates.
        first_script = echarts_scripts[0]
        for script in echarts_scripts[1:]:
            script.decompose()
        if first_script.parent != head:
            head.append(first_script)
        rewritten = True

    # 2. Wrap bare ECharts option object literals.
    for script in soup.find_all("script"):
        content = script.string
        if not content:
            continue
        if not _is_bare_object_literal(content):
            continue

        chart_id = _find_chart_container(script)
        if not chart_id:
            continue

        stripped = content.strip()
        new_script = (
            f"(function() {{\n"
            f"  var chartDom = document.getElementById('{chart_id}');\n"
            f"  if (!chartDom) return;\n"
            f"  var myChart = echarts.init(chartDom);\n"
            f"  var option = {stripped};\n"
            f"  myChart.setOption(option);\n"
            f"  window.addEventListener('resize', function() {{ myChart.resize(); }});\n"
            f"}})();"
        )
        script.string = new_script
        rewritten = True

    return str(soup) if rewritten else html


class RunCancelledError(RuntimeError):
    """本 run 已被用户取消（插话/停止）：报告管线应尽快中止。

    在管线阶段边界抛出，把浪费限定在当前阶段内的那一次 LLM 调用；
    错误文本明示"已被新指令取消、勿重试"，模型读到后不会再发起生成。
    """


def raise_if_run_cancelled() -> None:
    """若当前 run 的取消事件已置位则抛 RunCancelledError。

    取消事件经 request_context ContextVar 传递：run 启动时注入，
    stream_process task 创建时拷贝上下文，因此旧 run 的管线看到的是
    自己那一届的事件，不受新 run 同名 thread 的影响。
    """
    from src.agent_v3.request_context import get_request_context

    cancel_event = get_request_context().get("cancel_event")
    if cancel_event is not None and cancel_event.is_set():
        logger.warning(
            "报告管线阶段中止: run 已被取消（插话/停止），request_id=%s",
            get_request_context().get("request_id") or "-",
        )
        raise RunCancelledError(
            "REQUEST_CANCELLED：本次报告生成已被用户的新指令取消，请勿重试"
        )

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.infrastructure.converters.format_converter import convert_html

logger = logging.getLogger("njbank.agent")


def convert_report_html(html: str, target_format: str, output_path: str) -> str:
    return convert_html(html, target_format, output_path)


def write_report_html(html: str, output_path: str) -> str:
    """生成可独立打开的 HTML 报告；所有 HTML 下载入口统一调用这里。"""
    path = Path(output_path)
    path.write_text(prepare_report_html_for_download(html), encoding="utf-8")
    return str(path)


def prepare_report_html_for_download(html: str) -> str:
    """将报告整理为自包含 HTML，并内联运行图表所需的 ECharts 脚本。"""
    prepared = (html or "").strip()
    if not prepared:
        return ""
    prepared = _ensure_html_document(prepared)
    prepared = _inline_echarts_script(prepared)
    prepared = re.sub(
        r'(["\'])/lib/tabler-icons\.min\.css\1',
        r"\1./tabler-icons.min.css\1",
        prepared,
    )
    prepared = prepared.replace("/lib/tabler-icons.min.css", "./tabler-icons.min.css")
    return prepared


def _ensure_html_document(html: str) -> str:
    start_match = re.search(
        r"<(?:!doctype|html|section|div|body|head|main|article)\b",
        html,
        flags=re.IGNORECASE,
    )
    if start_match and start_match.start() > 0:
        html = html[start_match.start():]
    if re.search(r"<html\b", html, flags=re.IGNORECASE):
        return html
    return (
        "<!doctype html><html lang=\"zh-CN\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>活动分析报告</title>"
        "</head><body>"
        f"{html}"
        "</body></html>"
    )


def _inline_echarts_script(html: str) -> str:
    echarts_path = _static_lib_dir() / "echarts.min.js"
    if not echarts_path.exists():
        logger.warning("report export dependency missing: %s", echarts_path)
        return html

    script_text = echarts_path.read_text(encoding="utf-8")
    inline_script = f"<script>\n{script_text.replace('</script', '<\\/script')}\n</script>"
    script_pattern = re.compile(
        r"<script\b[^>]*\bsrc=[\"'][^\"']*echarts[^\"']*\.js[^\"']*[\"'][^>]*>\s*</script>",
        flags=re.IGNORECASE,
    )
    html, count = script_pattern.subn(lambda _: inline_script, html, count=1)
    if count:
        return script_pattern.sub("", html)
    if re.search(r"</head\s*>", html, flags=re.IGNORECASE):
        return re.sub(
            r"</head\s*>",
            lambda _: f"{inline_script}</head>",
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    return f"{inline_script}\n{html}"


def _static_lib_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "infrastructure" / "static" / "lib"

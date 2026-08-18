from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup

from src.report_pipeline.capabilities.utils import _is_bare_object_literal

if TYPE_CHECKING:
    from src.report_pipeline.state import AgentState
else:
    AgentState = dict

logger = logging.getLogger("njbank.agent")

REPORT_HTML_GUARD_FAILURE_MESSAGE = "当前模型访问量较大，请稍后重试。"
_GENERATION_STEPS = {"marketing_report_synthesis", "report_generation"}
_MARKDOWN_HEADING_RE = re.compile(r"(?m)^\s{0,3}#{1,6}\s+\S")
_MARKDOWN_HR_RE = re.compile(r"(?m)^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_MOJIBAKE_RE = re.compile(r"[锟�]|(?:[æçåéè][\x80-\xbf]?|娲|鍙|鎬|绛|璇|佹|冨|€)")
_REPORT_TITLE_KEYWORDS = ("报告", "分析", "营销", "活动")
_NON_MAIN_TITLE_TEXT = {"报告摘要", "摘要", "优化建议", "目录"}
_FORBIDDEN_TERMS = ("快照",)


@dataclass(frozen=True)
class HtmlGuardIssue:
    code: str
    message: str


@dataclass(frozen=True)
class HtmlGuardResult:
    valid: bool
    issues: list[HtmlGuardIssue]

    def to_dict(self, *, retry_count: int, max_retries: int) -> dict:
        return {
            "valid": self.valid,
            "issues": [
                {"code": issue.code, "message": issue.message}
                for issue in self.issues
            ],
            "retry_count": retry_count,
            "max_retries": max_retries,
        }


def report_html_guard_node(state: AgentState) -> dict:
    from src.config import get_settings
    from src.services.agent_run_history_service import save_report_file

    html_report = state.get("html_report") or ""
    retry_count = int(state.get("report_html_guard_retry_count") or 0)
    max_retries = max(0, int(get_settings().report_html_guard_max_retries))

    result = validate_report_html(html_report)
    result_payload = result.to_dict(retry_count=retry_count, max_retries=max_retries)

    if result.valid:
        logger.info(
            "HTML report guard passed: request_id=%s retry_count=%d",
            state.get("request_id", ""),
            retry_count,
        )
        save_report_file(state.get("request_id", ""), html_report)
        return {
            "report_html_guard_result": result_payload,
            "report_html_guard_retry_requested": False,
            "report_html_guard_retry_step": "",
            "next_agent": "supervisor",
        }

    logger.warning(
        "HTML report guard failed: request_id=%s retry_count=%d max_retries=%d issues=%s",
        state.get("request_id", ""),
        retry_count,
        max_retries,
        [issue.code for issue in result.issues],
    )

    if retry_count < max_retries:
        retry_step = _previous_generation_step(state.get("plan") or [])
        return {
            "html_report": "",
            "final_response": "",
            "report_html_guard_result": result_payload,
            "report_html_guard_retry_count": retry_count + 1,
            "report_html_guard_retry_requested": True,
            "report_html_guard_retry_step": retry_step,
            "next_agent": "supervisor",
        }

    return {
        "html_report": "",
        "final_response": REPORT_HTML_GUARD_FAILURE_MESSAGE,
        "report_html_guard_result": result_payload,
        "report_html_guard_retry_requested": False,
        "report_html_guard_retry_step": "",
        "next_agent": "supervisor",
        "report_history_enabled": False,
    }


def build_report_html_retry_instruction(state: AgentState) -> str:
    result = state.get("report_html_guard_result") or {}
    issues = result.get("issues") or []
    if not issues:
        return ""
    issue_text = "；".join(
        str(issue.get("message") or issue.get("code") or issue)
        for issue in issues[:8]
    )
    return f"""

重要：上一次生成的 HTML 未通过展示检查，问题包括：{issue_text}
请重新生成可直接展示的完整 HTML 文档，必须满足：
1. 以 <!DOCTYPE html> 开始，包含 <html lang="zh-CN">、<head>、<meta charset="UTF-8">、<body>。
2. 不要输出 Markdown 标题、分割线、代码块围栏或解释性前后缀。
3. ECharts 图表脚本必须使用可执行 JavaScript，不要输出裸对象字面量。
4. 中文必须保持 UTF-8 正常文本，不要输出乱码。
5. 页面顶部必须有可见主标题，例如 <h1>个客营销活动分析报告</h1>，不能只有浏览器 <title>。
6. 报告正文任何位置（标题、章节名、图表标题、表头、正文、注释）都不得出现“快照”字眼。
"""


def validate_report_html(html_report: str) -> HtmlGuardResult:
    issues: list[HtmlGuardIssue] = []
    html = (html_report or "").strip()
    if not html:
        issues.append(HtmlGuardIssue("empty_html", "HTML report is empty."))
        return HtmlGuardResult(False, issues)

    if not re.search(r"<[a-zA-Z][\w:-]*(?:\s|>|/>)", html):
        issues.append(HtmlGuardIssue("not_html", "Report does not contain valid HTML tags."))
        return HtmlGuardResult(False, issues)

    soup = BeautifulSoup(html, "html.parser")
    text_without_scripts = _remove_script_and_style_text(html)

    if not soup.find("html"):
        issues.append(HtmlGuardIssue("missing_html_tag", "Missing <html> root tag."))
    if not soup.find("head"):
        issues.append(HtmlGuardIssue("missing_head_tag", "Missing <head> tag."))
    if not soup.find("body"):
        issues.append(HtmlGuardIssue("missing_body_tag", "Missing <body> tag."))
    if not _has_utf8_charset(soup):
        issues.append(HtmlGuardIssue("missing_utf8_charset", "Missing UTF-8 charset declaration."))
    if not _has_visible_report_title(soup):
        issues.append(HtmlGuardIssue("missing_visible_report_title", "Missing visible report title in the page body."))

    if _MARKDOWN_HEADING_RE.search(text_without_scripts):
        issues.append(HtmlGuardIssue("markdown_heading_leftover", "Markdown heading markers remain in HTML."))
    if _MARKDOWN_HR_RE.search(text_without_scripts):
        issues.append(HtmlGuardIssue("markdown_rule_leftover", "Markdown horizontal rule markers remain in HTML."))
    if "```" in text_without_scripts:
        issues.append(HtmlGuardIssue("code_fence_leftover", "Markdown code fences remain in HTML."))

    mojibake_count = len(_MOJIBAKE_RE.findall(text_without_scripts))
    if mojibake_count >= 5:
        issues.append(HtmlGuardIssue("suspected_mojibake", "Report text appears to contain mojibake."))

    for term in _FORBIDDEN_TERMS:
        if term in text_without_scripts:
            issues.append(HtmlGuardIssue(
                "forbidden_term",
                f"报告正文出现禁用词“{term}”，请删除或改用“数据概览”“数据明细”等表述后重新生成。",
            ))

    issues.extend(_validate_chart_scripts(soup))
    return HtmlGuardResult(not issues, issues)


def _remove_script_and_style_text(html: str) -> str:
    return re.sub(r"<(script|style)\b[\s\S]*?</\1>", "", html, flags=re.IGNORECASE)


def _has_utf8_charset(soup: BeautifulSoup) -> bool:
    for meta in soup.find_all("meta"):
        charset = str(meta.get("charset") or "").lower().replace("-", "")
        content = str(meta.get("content") or "").lower().replace("-", "")
        if charset == "utf8" or "charset=utf8" in content:
            return True
    return False


def _has_visible_report_title(soup: BeautifulSoup) -> bool:
    body = soup.find("body") or soup
    selectors = [
        "h1",
        "header",
        ".report-title",
        ".report-header",
        ".page-title",
        ".title",
        "[class*='report-title']",
        "[class*='report-header']",
        "[class*='page-title']",
        "[class*='title']",
        "[id*='report-title']",
        "[id*='title']",
    ]
    for selector in selectors:
        for tag in body.select(selector):
            if _is_visible_report_title_text(tag.get_text(" ", strip=True)):
                return True
    return False


def _is_visible_report_title_text(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text or "")
    if len(normalized) < 6:
        return False
    if normalized in _NON_MAIN_TITLE_TEXT:
        return False
    if normalized.startswith(("一、", "二、", "三、", "四、", "五、", "1.", "1、")):
        return False
    return any(keyword in normalized for keyword in _REPORT_TITLE_KEYWORDS)


def _validate_chart_scripts(soup: BeautifulSoup) -> list[HtmlGuardIssue]:
    issues: list[HtmlGuardIssue] = []
    chart_divs = [
        tag for tag in soup.find_all("div")
        if str(tag.get("id") or "").lower().startswith("chart")
    ]
    scripts = soup.find_all("script")
    inline_scripts = [script for script in scripts if not script.get("src")]

    if chart_divs:
        has_echarts_loader = any(
            "echarts" in str(script.get("src") or "").lower()
            for script in scripts
        )
        has_inline_echarts = any("echarts.init" in (script.string or "") for script in inline_scripts)
        if not (has_echarts_loader or has_inline_echarts):
            issues.append(HtmlGuardIssue("missing_echarts_loader", "Chart containers exist without ECharts loader/init script."))

    for index, script in enumerate(inline_scripts, start=1):
        content = script.string or script.get_text() or ""
        if not content.strip():
            continue
        if _is_bare_object_literal(content):
            issues.append(HtmlGuardIssue("bare_script_object", f"Inline script {index} is a bare object literal."))
            continue
        if not _script_text_balanced(content):
            issues.append(HtmlGuardIssue("script_unbalanced", f"Inline script {index} has unbalanced quotes or brackets."))

    return issues


def _script_text_balanced(script: str) -> bool:
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    in_string = ""
    escaped = False
    in_line_comment = False
    in_block_comment = False

    for index, char in enumerate(script):
        next_char = script[index + 1] if index + 1 < len(script) else ""

        if in_line_comment:
            if char in "\r\n":
                in_line_comment = False
            continue
        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
            continue
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = ""
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            continue
        if char in ("'", '"', "`"):
            in_string = char
            continue
        if char in "([{":
            stack.append(char)
            continue
        if char in pairs:
            if not stack or stack.pop() != pairs[char]:
                return False

    return not stack and not in_string and not in_block_comment


def _previous_generation_step(plan: list[dict]) -> str:
    guard_index = -1
    for index, step in enumerate(plan):
        if step.get("step") == "report_html_guard" and step.get("status") == "running":
            guard_index = index
            break
    search_space = plan[:guard_index] if guard_index >= 0 else plan
    for step in reversed(search_space):
        name = step.get("step", "")
        if name in _GENERATION_STEPS:
            return name
    return "marketing_report_synthesis"

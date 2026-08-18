from __future__ import annotations

import re


# 报告页脚/尾注（"数据来源：…"、"报告生成时间：…"、"仅供内部参考"等）。
# prompt 已禁止 LLM 输出此类内容，但措辞多变拦不住，这里做后处理兜底。
_FOOTER_SOURCE_PATTERN = r"(?:报告生成时间[:：][^<\n\r]*)?数据来源[:：][^<\n\r]*"
_FOOTER_BASIS_PATTERN = r"报告基于[^<\n\r]*?生成[^<\n\r]*"


def strip_report_footer_note(html: str) -> str:
    """剥离报告末尾"数据来源/报告生成时间/仅供内部参考"一类的页脚、尾注。"""
    if not html:
        return html
    for text_pattern in (_FOOTER_SOURCE_PATTERN, _FOOTER_BASIS_PATTERN):
        # 先删除整标签包裹的页脚行，再删除裸露的文本行
        html = re.sub(
            rf"\s*<(p|div|footer|section|span)\b[^>]*>\s*{text_pattern}\s*</\1>\s*",
            "",
            html,
            flags=re.IGNORECASE,
        )
        html = re.sub(
            rf"^[ \t]*{text_pattern}[ \t]*(?:\r?\n)?",
            "",
            html,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    return html


BANK_REPORT_STYLE = """
<style>
  :root {
    --primary: #1a365d;
    --accent: #c9a84c;
    --bg: #f8f9fa;
    --card-bg: #ffffff;
    --text: #2d3748;
    --text-secondary: #8c8c8c;
    --success: #52c41a;
    --danger: #ff4d4f;
    --border: #e2e8f0;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
      "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    color: var(--text);
    background: var(--bg);
    line-height: 1.6;
  }
  .report-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 40px 24px;
  }
  .report-header {
    text-align: center;
    padding: 48px 0 32px;
    border-bottom: 3px solid var(--accent);
    margin-bottom: 40px;
  }
  .report-header h1 {
    font-size: 28px;
    color: var(--primary);
    margin-bottom: 8px;
  }
  .report-header .subtitle {
    font-size: 14px;
    color: var(--text-secondary);
  }
  .section {
    margin-bottom: 40px;
  }
  .section-title {
    font-size: 20px;
    color: var(--primary);
    padding-left: 12px;
    border-left: 4px solid var(--accent);
    margin-bottom: 20px;
  }
  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }
  .metric-card {
    background: var(--card-bg);
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    transition: box-shadow 0.2s;
  }
  .metric-card:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.10);
  }
  .metric-card .label {
    font-size: 14px;
    color: var(--text-secondary);
    margin-bottom: 8px;
  }
  .metric-card .value {
    font-size: 28px;
    font-weight: 700;
    color: var(--primary);
    margin-bottom: 8px;
  }
  .metric-card .change {
    font-size: 13px;
  }
  .metric-card .change.up { color: var(--success); }
  .metric-card .change.down { color: var(--danger); }
  .metric-card .change.stable { color: var(--text-secondary); }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    background: var(--card-bg);
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }
  th, td {
    padding: 12px 16px;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }
  th {
    background: var(--primary);
    color: #ffffff;
    font-weight: 600;
    font-size: 13px;
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #f7fafc; }
</style>
"""


def assemble_html_report(
    title: str,
    sections: list[str],
    include_summary: bool = True,
    include_recommendations: bool = True,
) -> str:
    sections_html = "\n".join(
        f'<div class="section">{s}</div>' for s in sections
    )

    summary_block = ""
    if include_summary:
        summary_block = """
        <div class="section">
          <h2 class="section-title">报告摘要</h2>
          <p style="color: var(--text-secondary); font-size: 15px;">
            本报告基于上传的活动数据，通过自动化分析流程生成"
            报告涵盖活动核心指标概览及深度分析结果，为决策提供数据支持"
          </p>
        </div>
        """

    recommendations_block = ""
    if include_recommendations:
        recommendations_block = """
        <div class="section">
          <h2 class="section-title">优化建议</h2>
          <p style="color: var(--text-secondary); font-size: 15px;">
            建议结合各指标变化趋势，重点关注转化率提升和成本优化方向"
            持续迭代活动策略以提升整体ROI"
          </p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  {BANK_REPORT_STYLE}
</head>
<body>
  <div class="report-container">
    <div class="report-header">
      <h1>{title}</h1>
      <p class="subtitle">活动分析助手 · 自动生成</p>
    </div>
    {summary_block}
    {sections_html}
    {recommendations_block}
  </div>
</body>
</html>"""

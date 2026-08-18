from pathlib import Path

import pytest

from src.report_pipeline.capabilities.report_layout_guard import (
    auto_fix_chart_layout,
    detect_layout_antipatterns,
    normalize_content_card_layout,
    normalize_metric_card_layout,
)

FIXTURES = Path(__file__).parent / "fixtures" / "report-layout"


@pytest.fixture
def bad_html() -> str:
    return (FIXTURES / "flex-direct-chart.html").read_text(encoding="utf-8")


@pytest.fixture
def good_html() -> str:
    return (FIXTURES / "grid-wrapped-chart.html").read_text(encoding="utf-8")


def test_detect_flex_direct_chart_antipattern(bad_html: str) -> None:
    findings = detect_layout_antipatterns(bad_html)
    types = {f["type"] for f in findings}
    assert "flex_direct_chart" in types


def test_detect_percentage_height_antipattern(bad_html: str) -> None:
    findings = detect_layout_antipatterns(bad_html)
    types = {f["type"] for f in findings}
    assert "percentage_height" in types


def test_good_html_has_no_antipatterns(good_html: str) -> None:
    findings = detect_layout_antipatterns(good_html)
    assert findings == []


def test_auto_fix_adds_wrapper_and_explicit_height(bad_html: str) -> None:
    fixed = auto_fix_chart_layout(bad_html)
    assert "chart-wrapper" in fixed
    assert "echarts-container" in fixed
    assert "height:360px" in fixed


def test_auto_fix_removes_antipatterns(bad_html: str) -> None:
    fixed = auto_fix_chart_layout(bad_html)
    findings = detect_layout_antipatterns(fixed)
    assert findings == []


def test_auto_fix_is_idempotent(bad_html: str) -> None:
    first = auto_fix_chart_layout(bad_html)
    second = auto_fix_chart_layout(first)
    assert first == second


def test_empty_html_returns_empty() -> None:
    assert auto_fix_chart_layout("") == ""
    assert detect_layout_antipatterns("") == []


def _metric_card(label: str, value: str, extra_class: str = "") -> str:
    return (
        f'<div class="metric-card {extra_class}" style="background:#fff; '
        f'border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,.06);">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f"</div>"
    )


def _card_row(*cards: str) -> str:
    return (
        '<div class="metric-row" style="display:flex; gap:16px; margin-bottom:16px;">'
        + "".join(cards)
        + "</div>"
    )


def test_normalize_merges_orphan_card_rows() -> None:
    row1 = _card_row(*[_metric_card(f"指标{i}", f"{i}00") for i in range(5)])
    orphan1 = _card_row(_metric_card("笔均交易额", "50.39 元"))
    row2 = _card_row(*[_metric_card(f"存款{i}", f"{i}00 万") for i in range(5)])
    orphan2 = _card_row(_metric_card("月日均AUM提升", "+1,305.78 万"))
    html = f"<html><body><section>{row1}{orphan1}{row2}{orphan2}</section></body></html>"

    fixed = normalize_metric_card_layout(html)

    assert fixed.count("metric-row") == 1
    assert fixed.count("metric-card") == 12
    assert "display:grid" in fixed
    assert "repeat(auto-fill, minmax(220px, 1fr))" in fixed
    assert "display:flex" not in fixed


def test_normalize_converts_flex_card_group_to_grid() -> None:
    html = (
        "<html><body>"
        + _card_row(*[_metric_card(f"指标{i}", f"{i}") for i in range(3)])
        + "</body></html>"
    )
    fixed = normalize_metric_card_layout(html)
    assert "display:grid" in fixed
    assert "gap:16px" in fixed
    # Few cards: auto-fit so the row is filled evenly.
    assert "repeat(auto-fit, minmax(260px, 1fr))" in fixed


def test_normalize_leaves_non_card_content_untouched() -> None:
    paragraph_html = (
        "<html><body><div>"
        "<p>本次活动共触达客户 1200 人，整体转化情况良好，各渠道表现存在差异，"
        "需要结合后续数据持续跟进转化效果。</p>"
        "<p>活动期间新增签约客户 340 人，主要来源于手机银行推送与外呼渠道，"
        "建议下期活动加大高意向客户的外呼频次。</p>"
        "</div></body></html>"
    )
    assert normalize_metric_card_layout(paragraph_html) == paragraph_html


def test_normalize_leaves_chart_containers_untouched() -> None:
    html = (
        "<html><body><section>"
        + _card_row(*[_metric_card(f"指标{i}", f"{i}") for i in range(3)])
        + '<div id="chart-1" style="width:100%;height:400px;"></div>'
        + '<script>(function(){var c=echarts.init(document.getElementById("chart-1"));c.setOption({});})();</script>'
        + "</section></body></html>"
    )
    fixed = normalize_metric_card_layout(html)
    assert 'id="chart-1"' in fixed
    assert "echarts.init" in fixed


def test_normalize_is_idempotent() -> None:
    row1 = _card_row(*[_metric_card(f"指标{i}", f"{i}") for i in range(4)])
    orphan = _card_row(_metric_card("笔均交易额", "50.39 元"))
    html = f"<html><body><section>{row1}{orphan}</section></body></html>"
    first = normalize_metric_card_layout(html)
    second = normalize_metric_card_layout(first)
    assert first == second


def test_normalize_empty_html() -> None:
    assert normalize_metric_card_layout("") == ""


def _content_card(title: str, body: str) -> str:
    return (
        '<div class="compare-card" style="width:400px; background:#f6fbf7; '
        'border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,.06); padding:20px;">'
        f'<div class="card-title">{title}</div>'
        f'<p>{body}</p>'
        "</div>"
    )


def _content_card_row(*cards: str) -> str:
    return (
        '<div class="compare-row" style="display:flex; gap:20px;">'
        + "".join(cards)
        + "</div>"
    )


def test_content_cards_stretch_to_fill_row() -> None:
    card_a = _content_card("最佳参考活动", "演示银行App6月促活营销，源名单客户数 545,213.58 户，多渠道协同。")
    card_b = _content_card("待改进参考活动", "五一节前理财营销，源名单客户数 64,563.58 户，触达渠道单一。")
    html = f"<html><body><section>{_content_card_row(card_a, card_b)}</section></body></html>"

    fixed = normalize_content_card_layout(html)

    assert "display:grid" in fixed
    assert "repeat(auto-fit, minmax(320px, 1fr))" in fixed
    assert "width:400px" not in fixed
    assert "display:flex" not in fixed


def test_content_card_row_leaves_stacked_blocks_untouched() -> None:
    card_a = _content_card("归因分析", "名单规模仅为前者的 11.8%，建议扩大圈定范围。")
    card_b = _content_card("活动启示", "建议结合两类活动优势形成组合打法。")
    # display:block container (stacked, not a side-by-side row) stays as is.
    html = (
        '<html><body><div style="display:block;">'
        + card_a
        + card_b
        + "</div></body></html>"
    )
    assert normalize_content_card_layout(html) == html


def test_content_card_row_leaves_metric_grid_untouched() -> None:
    row = _card_row(*[_metric_card(f"指标{i}", f"{i}") for i in range(3)])
    html = f"<html><body>{row}</body></html>"
    metric_fixed = normalize_metric_card_layout(html)
    assert normalize_content_card_layout(metric_fixed) == metric_fixed


def test_content_card_normalize_is_idempotent() -> None:
    card_a = _content_card("最佳参考活动", "演示银行App6月促活营销，源名单客户数 545,213.58 户。")
    card_b = _content_card("待改进参考活动", "五一节前理财营销，源名单客户数 64,563.58 户。")
    html = f"<html><body>{_content_card_row(card_a, card_b)}</body></html>"
    first = normalize_content_card_layout(html)
    second = normalize_content_card_layout(first)
    assert first == second


def test_content_card_row_ignores_chart_rows() -> None:
    chart_row = (
        '<div style="display:flex; gap:16px;">'
        '<div id="chart-1" style="width:50%;height:360px;"></div>'
        '<div id="chart-2" style="width:50%;height:360px;"></div>'
        "</div>"
    )
    html = f"<html><body>{chart_row}</body></html>"
    assert normalize_content_card_layout(html) == html

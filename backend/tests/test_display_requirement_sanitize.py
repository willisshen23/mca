"""display_requirement（SKILL 模板预览）脱敏测试。

根因背景：模板预览的「输出示例」中含大量具体示例数值/产品名，
原样注入报告生成提示词后，模型在 report_data 缺少对应数据时会照抄示例值。
sanitize_display_requirement 必须在保留结构指引的同时剥离这些示例数值。
"""

from src.domain.report.template_skill import sanitize_display_requirement


SAMPLE_TABLE_REQUIREMENT = """## OutputFormat:
- 输出内容包含两大块内容，分别是核心结论和外呼客群产品交易分析。

- 外呼客群产品交易分析需要以表格形式呈现存款、理财、整体的外呼总人数、点击人数、购买人数，并基于此输出结论。
## 输出示例：
## 二、外呼客群产品交易分析
|统计维度|理财相关数据|存款相关数据|整体汇总|
|---|---|---|---|
|外呼总人数|-|-|6538人|
|点击人数|351人|228人|579人|
|购买人数|76人|55人|131人|
|购买总金额|8353.60万元|14832.41万元|23186.01万元（2.32亿元）|
结论：
-【基于外呼所有客户产品交易数据的结论1】

- 有效通话客户产品偏好分析需要展示产品类型、产品名称、购买人数、购买金额，基于此输出相应结论。
## 输出示例：
## 四、有效通话客群产品偏好分析
|排名|产品类型|产品名称|购买人数|购买金额（万元）|
|---|---|---|---|---|
|1|存款|1到3年期普通定期|39|301.45|
|2|理财|南银理财悦稳最低持有7天2011号-A份额（专属）|19|32.78|
"""


SAMPLE_ASCII_CARD = """## InputFormat:
- 有效通话客户指通话时长大于30秒的客户，购买金额大于100万为高价值购买。
## 输出示例
## 一、北极星指标概览（数字卡片）
### 业务指标卡片
┌──────────────────────────────┐
│ 零售价值客户AUM (活动期间)      │
│ 32.6 亿 (+8.2% vs 日常)         │
└──────────────────────────────┘
│ 活动触达客户人数                │
│ 85,320 人                       │
"""


def test_table_data_rows_are_stripped_but_header_kept() -> None:
    result = sanitize_display_requirement(SAMPLE_TABLE_REQUIREMENT)
    # 表头结构保留
    assert "|统计维度|理财相关数据|存款相关数据|整体汇总|" in result
    # 示例数值被剥离
    for leaked in ("6538", "351", "579", "8353.60", "14832.41", "23186.01"):
        assert leaked not in result, f"示例数值 {leaked} 泄漏到提示词"


def test_product_names_in_example_tables_are_removed() -> None:
    result = sanitize_display_requirement(SAMPLE_TABLE_REQUIREMENT)
    assert "南银理财悦稳" not in result
    assert "301.45" not in result
    # 表头仍保留，供模型参考表格结构
    assert "产品名称" in result


def test_requirement_prose_outside_examples_keeps_numbers() -> None:
    result = sanitize_display_requirement(SAMPLE_ASCII_CARD)
    # 口径数字属于业务规则，必须保留
    assert "30秒" in result
    assert "100万" in result


def test_example_prose_numbers_are_masked() -> None:
    result = sanitize_display_requirement(SAMPLE_ASCII_CARD)
    assert "32.6" not in result
    assert "8.2" not in result
    assert "85,320" not in result
    # 结构标题保留
    assert "北极星指标概览" in result
    assert "活动触达客户人数" in result


def test_zone_resumes_at_each_example_marker() -> None:
    result = sanitize_display_requirement(SAMPLE_TABLE_REQUIREMENT)
    # 两个 输出示例 区块之间的要求正文不受影响
    assert "有效通话客户产品偏好分析需要展示产品类型" in result


def test_empty_and_none_input() -> None:
    assert sanitize_display_requirement("") == ""
    assert sanitize_display_requirement(None) == ""


def test_placeholder_bullets_are_kept() -> None:
    result = sanitize_display_requirement(SAMPLE_TABLE_REQUIREMENT)
    # 模板自带的占位符条目应保留（条目序号数字掩码为 X 不影响语义），作为结论条数参考
    assert "-【基于外呼所有客户产品交易数据的结论X】" in result

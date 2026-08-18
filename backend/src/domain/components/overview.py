from __future__ import annotations

from .base import AnalysisComponent
from .registry import ComponentRegistry


class OverviewComponent(AnalysisComponent):
    type = "overview"
    display_name = "活动概览"
    config_schema = {
        "type": "object",
        "properties": {
            "metrics": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "total_revenue",
                        "total_cost",
                        "participants",
                        "conversion_rate",
                        "avg_transaction",
                        "roi",
                        "active_users",
                        "new_users",
                        "retention_rate",
                        "arpu",
                    ],
                },
                "description": "需要分析的指标列表",
            }
        },
        "required": ["metrics"],
    }

    def get_analysis_prompt(self, component: dict, data_summary: str) -> str:
        title = component.get("title", "活动概览")
        config = component.get("config", {})
        metrics = config.get("metrics", ["total_revenue", "participants"])

        return f"""基于以下数据文件的结构和内容摘要"

{data_summary}

请针对「{title}」计算以下关键指标：
{', '.join(metrics)}

要求"
1. 对每个指标输出：指标名称、当前值、同比变化百分比、环比变化百分比
2. 如果数据中不包含某些指标的计算字段，请根据可用字段做合理推断
3. 输出格式"JSON，结构如下：
```json
{{
  "title": "{title}",
  "metrics": [
    {{
      "name": "指标名称",
      "value": "当前",
      "unit": "单位",
      "yoy_change": "同比变化",
      "mom_change": "环比变化",
      "trend": "up|down|stable"
    }}
  ]
}}
```
"""

    def get_report_prompt(self, component: dict, analysis_result: str) -> str:
        title = component.get("title", "活动概览")

        return f"""请根据以下分析结果，生成「{title}」章节的 HTML 片段。

分析结果：
{analysis_result}

要求：
1. 使用指标卡片网格展示核心数值。
2. 每张卡片包含指标名称、指标数值、趋势或简短解释。
3. 样式保持银行业务报告风格，结构清晰，可直接嵌入报告正文。
4. 只输出 HTML 片段，不要输出解释文本。
"""


overview = OverviewComponent()
ComponentRegistry.register(overview)

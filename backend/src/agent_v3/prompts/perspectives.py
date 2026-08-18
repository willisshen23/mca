"""预置分析视角定义（设计文档 §7 意图⑧）。

M1 阶段仅将 perspective 登记入 report_context；
M3 在 generate_report 的 seed 构建中把 prompt_excerpt 注入 marketing_intent.scene，
从而影响数据模板匹配与报告合成（旧节点零改动）。
"""
from __future__ import annotations

PERSPECTIVES: dict[str, dict] = {
    "outbound_call_analysis": {
        "display_name": "外呼活动分析",
        "focus_metrics": ["接通率", "挂机率", "通话时长分布", "外呼时段效率", "脚本转化对比"],
        "prompt_excerpt": (
            "以外呼活动分析视角生成专项报告，重点覆盖：接通率、挂机率、"
            "通话时长分布、外呼时段效率、脚本转化对比"
        ),
        "template_keyword": "外呼",
    },
    "sms_analysis": {
        "display_name": "短信活动分析",
        "focus_metrics": ["点击率", "退订率", "发送时段", "链接转化", "A/B文案效果"],
        "prompt_excerpt": (
            "以短信营销分析视角生成专项报告，重点覆盖：点击率、退订率、"
            "发送时段效果、链接转化、A/B文案效果对比"
        ),
        "template_keyword": "短信",
    },
    "comprehensive_operations": {
        "display_name": "综合运营分析",
        "focus_metrics": ["ROI", "CPA", "渠道占比", "活动排期冲突", "客群重叠度"],
        "prompt_excerpt": (
            "以综合运营分析视角生成专项报告，重点覆盖：ROI、CPA、渠道占比、"
            "活动排期冲突、客群重叠度"
        ),
        "template_keyword": "综合",
    },
}


def get_perspective(key: str) -> dict | None:
    return PERSPECTIVES.get((key or "").strip())


def perspective_keys_text() -> str:
    """供 System Prompt / 工具错误信息使用的可选视角清单文本。"""
    return "、".join(f"{key}（{cfg['display_name']}）" for key, cfg in PERSPECTIVES.items())

from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "你是银行内网 Python 应用的运维诊断助手。值班人员不懂 Python，"
    "你的结论必须让非技术人员也能照着操作。\n"
    "基于给定的检查项、系统证据包和运维手册，输出**严格 JSON**（不要输出其他内容）：\n"
    '{"causes": [{"cause": "可能原因", "confidence": "高|中|低", "basis": "判断依据（引用证据）"}], '
    '"suggestions": [{"step": "第一步做什么", "detail": "具体操作，涉及文件给完整路径"}]}\n'
    "规则：原因按置信度从高到低排序；建议按操作顺序排列；"
    "只允许建议人工操作，你不执行任何动作；证据不足时在 basis 中明说。"
)

_TEMPLATE = """## 异常检查项
- ID：{check_id}
- 名称：{check_title}
- 级别：{check_level}
- 规则判定：{check_message}

## 运维手册
{runbook}

## 系统证据包（JSON）
{evidence_json}

请输出诊断结论 JSON。"""


def render_diagnosis_messages(check: dict, evidence: dict, runbook_body: str) -> list[dict]:
    user = _TEMPLATE.format(
        check_id=check.get("id", ""),
        check_title=check.get("title", ""),
        check_level=check.get("level", ""),
        check_message=check.get("message", ""),
        runbook=runbook_body or "（无匹配运维手册）",
        evidence_json=json.dumps(evidence, ensure_ascii=False, indent=2),
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]

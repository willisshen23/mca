from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

from src.collectors import COLLECTORS
from src.collectors.base import run_collector
from src.diagnosis.evidence import build_evidence, truncate_evidence
from src.diagnosis.llm import chat
from src.diagnosis.prompts import render_diagnosis_messages


@dataclass
class Playbook:
    check_id: str
    title: str
    collectors: tuple
    runbook_category: str


PLAYBOOKS = {
    "process-alive": Playbook("process-alive", "进程宕机诊断", ("process", "logs"), "process-down"),
    "health-timeout": Playbook("health-timeout", "健康检查超时诊断", ("process", "logs", "system"), "health-slow"),
    "log-error-spike": Playbook("log-error-spike", "错误日志突增诊断", ("logs", "process", "llm_gateway", "bank_api", "database"), "error-spike"),
    "disk-usage": Playbook("disk-usage", "磁盘水位诊断", ("system",), "disk-full"),
    "mysql-unreachable": Playbook("mysql-unreachable", "数据库不可达诊断", ("database", "logs"), "mysql-unreachable"),
    "llm-latency": Playbook("llm-latency", "LLM 网关延迟诊断", ("llm_gateway", "logs"), "llm-timeout"),
    "bank-api": Playbook("bank-api", "银行接口异常诊断", ("bank_api", "logs"), "bank-api"),
}

DEFAULT_PLAYBOOK = Playbook(
    "*", "通用诊断",
    ("process", "logs", "system", "database", "llm_gateway", "bank_api"),
    "general",
)


def parse_conclusion(text: str) -> dict:
    """容错解析 LLM 输出：直接 JSON → ```json 代码块 → 原文兜底。"""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return {"raw": text}


def _find_check(db, check_id: str) -> dict:
    snapshot = db.latest_snapshot()
    if snapshot:
        for check in snapshot["payload"].get("checks", []):
            if check["id"] == check_id:
                return check
    return {"id": check_id, "title": check_id, "level": "gray", "message": "（无巡检快照）"}


async def run_diagnosis(db, settings, check_id, *, chat_fn=None, collectors=None) -> dict:
    """预编排诊断：剧本选采集器 → 证据包 → 单次 LLM 调用；LLM 失败则降级。"""
    chat_fn = chat_fn or chat
    collectors = collectors or COLLECTORS
    playbook = PLAYBOOKS.get(check_id, DEFAULT_PLAYBOOK)

    check = _find_check(db, check_id)
    samples_list = await asyncio.gather(*(
        run_collector(name, collectors[name], settings)
        for name in playbook.collectors
        if name in collectors
    ))
    samples = {s.collector: s for s in samples_list}
    evidence = truncate_evidence(
        build_evidence(check, samples, settings), settings.evidence_token_budget
    )
    runbook = db.get_runbook_by_category(playbook.runbook_category)
    runbook_body = runbook["body"] if runbook else ""
    messages = render_diagnosis_messages(check, evidence, runbook_body)

    degraded = False
    error = None
    reply = ""
    conclusion: dict = {}
    try:
        reply = await chat_fn(settings, messages)
        conclusion = parse_conclusion(reply)
    except Exception as exc:  # noqa: BLE001 - 降级是设计意图
        degraded = True
        error = f"{type(exc).__name__}: {exc}"

    transcript = list(messages)
    if reply:
        transcript.append({"role": "assistant", "content": reply})
    diagnosis_id = db.save_diagnosis(
        check_id, playbook.title,
        json.dumps(conclusion, ensure_ascii=False),
        json.dumps(transcript, ensure_ascii=False),
        degraded, error,
    )

    result = {"id": diagnosis_id, "check_id": check_id, "degraded": degraded}
    if degraded:
        result.update({
            "rule_message": check.get("message", ""),
            "runbook": runbook_body,
            "error": error,
        })
    else:
        result["conclusion"] = conclusion
    return result


async def followup(db, settings, diagnosis_id, question, *, chat_fn=None) -> dict:
    """追问：历史 transcript + 新问题 → 单次 LLM 调用，双方消息落库。"""
    chat_fn = chat_fn or chat
    diag = db.get_diagnosis(diagnosis_id)
    if diag is None:
        raise KeyError(f"诊断记录 {diagnosis_id} 不存在")
    transcript = json.loads(diag["transcript"])
    transcript.append({"role": "user", "content": question})
    answer = await chat_fn(settings, transcript)
    db.append_message(diagnosis_id, "user", question)
    db.append_message(diagnosis_id, "assistant", answer)
    return {"id": diagnosis_id, "answer": answer}

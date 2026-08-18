from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from src.rules.builtins import JUDGES


@dataclass
class Rule:
    id: str
    title: str
    collector: str
    judge: str
    params: dict = field(default_factory=dict)


@dataclass
class CheckResult:
    id: str
    title: str
    level: str
    message: str


def load_rules(path) -> list[Rule]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    return [
        Rule(
            id=item["id"],
            title=item["title"],
            collector=item["collector"],
            judge=item["judge"],
            params=item.get("params") or {},
        )
        for item in raw
    ]


def evaluate(samples: dict, rules: list[Rule]) -> list[CheckResult]:
    results = []
    for rule in rules:
        sample = samples.get(rule.collector)
        if sample is None:
            results.append(CheckResult(rule.id, rule.title, "gray", "采集器未执行"))
            continue
        if not sample.ok:
            results.append(CheckResult(rule.id, rule.title, "gray", f"采集失败：{sample.error}"))
            continue
        verdict = JUDGES[rule.judge](sample, rule.params)
        if verdict is None:
            results.append(CheckResult(rule.id, rule.title, "green", "正常"))
        else:
            level, message = verdict
            results.append(CheckResult(rule.id, rule.title, level, message))
    return results

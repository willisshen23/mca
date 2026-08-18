from __future__ import annotations

from pathlib import Path

from src.collectors.base import Sample
from src.rules.builtins import JUDGES
from src.rules.engine import Rule, evaluate, load_rules

RULES_YAML = """
- id: process-alive
  title: 主应用进程存活
  collector: process
  judge: process_alive
- id: disk-usage
  title: 磁盘水位
  collector: system
  judge: disk_usage
  params: {warn_pct: 85, red_pct: 95}
"""


def _write_rules(tmp_path) -> Path:
    p = tmp_path / "rules.yaml"
    p.write_text(RULES_YAML)
    return p


def test_load_rules(tmp_path):
    rules = load_rules(_write_rules(tmp_path))
    assert rules[0].id == "process-alive"
    assert rules[1].params == {"warn_pct": 85, "red_pct": 95}


def test_evaluate_green_when_judge_returns_none(tmp_path):
    rules = load_rules(_write_rules(tmp_path))
    samples = {
        "process": Sample("process", True, metrics={"alive": True}),
        "system": Sample("system", True, metrics={"disk_pct": 50.0}),
    }
    checks = evaluate(samples, rules)
    assert [c.level for c in checks] == ["green", "green"]
    assert checks[0].message == "正常"


def test_evaluate_red_and_yellow(tmp_path):
    rules = load_rules(_write_rules(tmp_path))
    samples = {
        "process": Sample("process", True, metrics={"alive": False, "pid": None}),
        "system": Sample("system", True, metrics={"disk_pct": 88.0}),
    }
    checks = evaluate(samples, rules)
    assert checks[0].level == "red" and "进程" in checks[0].message
    assert checks[1].level == "yellow" and "88" in checks[1].message


def test_evaluate_yellow_when_pid_missing_but_health_ok(tmp_path):
    rules = load_rules(_write_rules(tmp_path))
    samples = {
        "process": Sample("process", True, metrics={"alive": False, "pid": None, "health_ok": True}),
        "system": Sample("system", True, metrics={"disk_pct": 50.0}),
    }
    checks = evaluate(samples, rules)
    assert checks[0].level == "yellow"
    assert "pid 文件缺失" in checks[0].message


def test_evaluate_gray_when_collector_failed(tmp_path):
    rules = load_rules(_write_rules(tmp_path))
    samples = {"process": Sample("process", False, error="TimeoutError: x")}
    checks = evaluate(samples, rules)
    assert checks[0].level == "gray"
    assert "TimeoutError" in checks[0].message
    assert checks[1].level == "gray" and checks[1].message == "采集器未执行"


def test_judge_log_error_spike():
    judge = JUDGES["log_error_spike"]
    params = {"warn_min": 5, "red_min": 20}
    assert judge(Sample("logs", True, metrics={"error_count": 0, "error_count_yesterday": 0}), params) is None
    level, _ = judge(Sample("logs", True, metrics={"error_count": 8, "error_count_yesterday": 2}), params)
    assert level == "yellow"
    level, _ = judge(Sample("logs", True, metrics={"error_count": 30, "error_count_yesterday": 3}), params)
    assert level == "red"


def test_judge_llm_latency():
    judge = JUDGES["llm_latency"]
    params = {"warn_s": 10, "red_s": 30}
    level, msg = judge(Sample("llm_gateway", True, metrics={"reachable": False, "error": "x"}), params)
    assert level == "red"
    level, _ = judge(Sample("llm_gateway", True, metrics={"reachable": True, "latency_s": 45}), params)
    assert level == "red"
    level, _ = judge(Sample("llm_gateway", True, metrics={"reachable": True, "latency_s": 15}), params)
    assert level == "yellow"
    assert judge(Sample("llm_gateway", True, metrics={"reachable": True, "latency_s": 2}), params) is None


def test_builtin_rules_yaml_loads_and_judges_exist():
    rules = load_rules(Path(__file__).resolve().parents[1] / "src" / "rules" / "rules.yaml")
    assert len(rules) == 7
    for rule in rules:
        assert rule.judge in JUDGES, f"{rule.id} 引用了不存在的 judge {rule.judge}"

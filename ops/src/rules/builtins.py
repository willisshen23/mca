from __future__ import annotations


def process_alive(sample, params):
    m = sample.metrics
    if m.get("alive"):
        return None
    if m.get("pid") is None and m.get("health_ok"):
        return ("yellow", "pid 文件缺失（进程可能由 start-offline.sh 前台方式启动，健康检查正常）")
    pid = m.get("pid")
    hint = f"pid={pid}" if pid else "pid 文件缺失或为空"
    return ("red", f"主应用进程不存在（{hint}）")


def health_latency(sample, params):
    m = sample.metrics
    if not m.get("health_ok"):
        status = m.get("health_status")
        return ("red", f"健康检查失败（{'HTTP ' + str(status) if status else '无响应'}）")
    latency = m.get("health_latency_ms") or 0
    if latency >= params.get("red_ms", 10000):
        return ("red", f"健康检查严重超时（{latency}ms）")
    if latency >= params.get("warn_ms", 2000):
        return ("yellow", f"健康检查偏慢（{latency}ms）")
    return None


def log_error_spike(sample, params):
    now = sample.metrics.get("error_count", 0)
    yesterday = sample.metrics.get("error_count_yesterday", 0)
    warn_min = params.get("warn_min", 5)
    red_min = params.get("red_min", 20)
    baseline = max(yesterday, 1)
    if now >= red_min and now > 3 * baseline:
        return ("red", f"错误日志突增：当前窗口 {now} 条，昨日同时段 {yesterday} 条")
    if now >= warn_min and now > baseline:
        return ("yellow", f"错误日志增多：当前窗口 {now} 条，昨日同时段 {yesterday} 条")
    return None


def disk_usage(sample, params):
    pct = sample.metrics.get("disk_pct")
    if pct is None:
        return None
    if pct >= params.get("red_pct", 95):
        return ("red", f"磁盘使用率 {pct}%（{sample.metrics.get('disk_path', '')}）")
    if pct >= params.get("warn_pct", 85):
        return ("yellow", f"磁盘使用率 {pct}%（{sample.metrics.get('disk_path', '')}）")
    return None


def mysql_reachable(sample, params):
    m = sample.metrics
    if m.get("mode") == "mysql" and not m.get("reachable"):
        return ("red", f"MySQL 不可达：{m.get('error') or '未知原因'}")
    if m.get("mode") == "sqlite" and not m.get("reachable"):
        return ("red", "SQLite 数据目录不存在或无可读 .db 文件")
    return None


def llm_latency(sample, params):
    m = sample.metrics
    if not m.get("reachable"):
        return ("red", f"LLM 网关不可达：{m.get('error') or '未配置'}")
    latency = m.get("latency_s") or 0
    if latency >= params.get("red_s", 30):
        return ("red", f"LLM 网关响应严重超时（{latency}s）")
    if latency >= params.get("warn_s", 10):
        return ("yellow", f"LLM 网关响应偏慢（{latency}s）")
    return None


def bank_api(sample, params):
    endpoints = sample.metrics.get("endpoints", [])
    down = [e for e in endpoints if not e.get("reachable")]
    if down:
        urls = "、".join(e["url"] for e in down)
        return ("red", f"{len(down)} 个银行接口不可达：{urls}")
    bad = [e for e in endpoints if (e.get("status") or 0) >= 500]
    if bad:
        urls = "、".join(f"{e['url']}(HTTP {e['status']})" for e in bad)
        return ("yellow", f"银行接口返回 5xx：{urls}")
    return None


JUDGES = {
    "process_alive": process_alive,
    "health_latency": health_latency,
    "log_error_spike": log_error_spike,
    "disk_usage": disk_usage,
    "mysql_reachable": mysql_reachable,
    "llm_latency": llm_latency,
    "bank_api": bank_api,
}

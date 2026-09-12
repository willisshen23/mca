"""P4 离线包业务冒烟：健康检查 → 对话(查询工具) → 审批 approve → 报告生成。

容器内执行（venv python，httpx 由 openai 传递依赖提供）：
    backend/venv/bin/python /smoke.py
退出码 0 = 全部通过；任一断言失败即非零退出。
"""
import json
import os
import sys
import uuid

import httpx

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:8000")
USER_ID = "p4smoke"
PIPELINE_STEPS = {
    "selected_activity_router", "outbound_activity_data_fetch", "template_list_fetch",
    "template_matching", "component_value_fetch", "component_value_cleanup",
    "activity_template_matching", "uploaded_component_value_extract",
    "marketing_report_synthesis",
}
TIMEOUT = httpx.Timeout(1300.0, connect=10.0)  # 读超时须 > 应用侧 LLM_TIMEOUT_SECONDS=1200


def fail(msg: str) -> "None":
    print(f"[SMOKE-FAIL] {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"[SMOKE-OK] {msg}")


def _post_stream(path: str, payload: dict) -> list:
    frames = []
    with httpx.stream("POST", f"{BASE}{path}", json=payload, timeout=TIMEOUT) as resp:
        if resp.status_code != 200:
            fail(f"{path} HTTP {resp.status_code}: {resp.read().decode()[:500]}")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                try:
                    frames.append(json.loads(line[len("data: "):]))
                except json.JSONDecodeError:
                    pass
    return frames


def run(thread_id: str, message: str) -> list:
    return _post_stream("/activity/api/v2/agent/run", {
        "thread_id": thread_id, "message": message, "original_user_text": message,
        "user_id": USER_ID, "org_no": "001", "channel": "AILMIS",
    })


def resume_approve(thread_id: str, tool: str) -> list:
    return _post_stream("/activity/api/v2/agent/resume", {
        "thread_id": thread_id, "decision": "approve", "tool": tool,
        "user_id": USER_ID, "org_no": "001", "channel": "AILMIS",
    })


def last_done(frames: list) -> dict:
    dones = [f for f in frames if f.get("type") == "done"]
    return dones[-1] if dones else {}


def run_with_approvals(thread_id: str, message: str, max_rounds: int = 6) -> list:
    """跑一轮对话；遇 approval_required 自动 approve，直至 done.awaiting_approval=False。"""
    frames = run(thread_id, message)
    all_frames = list(frames)
    for _ in range(max_rounds):
        done = last_done(all_frames)
        if not done:
            fail("流中缺少 done 帧")
        if not done.get("payload", {}).get("awaiting_approval"):
            return all_frames
        approvals = [f for f in frames if f.get("type") == "approval_required"]
        if not approvals:
            fail("awaiting_approval=True 但缺少 approval_required 帧")
        tool = str(approvals[-1].get("payload", {}).get("tool", ""))
        print(f"[SMOKE] 自动 approve: {tool}")
        frames = resume_approve(thread_id, tool)
        all_frames.extend(frames)
    fail("审批轮次超过上限")
    return all_frames  # unreachable


def main() -> None:
    # 1. 健康检查
    resp = httpx.get(f"{BASE}/activity/health", timeout=10.0)
    if resp.status_code != 200:
        fail(f"/activity/health HTTP {resp.status_code}")
    ok("健康检查")

    # 1.5 前端新鲜度：首页可访问且引用的是宿主机当前构建的哈希资产
    expected_asset = os.environ.get("EXPECTED_ASSET", "").strip()
    if expected_asset:
        resp = httpx.get(f"{BASE}/", timeout=10.0)
        if resp.status_code != 200:
            fail(f"/ HTTP {resp.status_code}（前端页面不可访问）")
        if expected_asset not in resp.text:
            fail(f"首页未引用期望资产 {expected_asset}（疑似服务了旧前端）")
        ok("前端页面可访问且为最新构建")
    else:
        print("[SMOKE] EXPECTED_ASSET 未设置，跳过前端新鲜度断言")

    thread = f"p4-{uuid.uuid4().hex[:8]}"

    # 2. 对话 + 查询工具
    frames = run_with_approvals(thread, "请使用工具查询当前有哪些营销活动，列出名称")
    nodes = {str(f.get("node")) for f in frames if f.get("type") == "node_update"}
    if "search_activities" not in nodes:
        fail(f"未观察到 search_activities 工具帧，实际 node: {sorted(nodes)}")
    ok("对话 + search_activities 工具调用")

    # 3. 审批 approve（显式断言审批帧，再 approve）
    frames = run(thread, "把查询结果里的第一个活动加入分析队列")
    approvals = [f for f in frames if f.get("type") == "approval_required"]
    if not approvals:
        fail("未触发 add_to_analysis_queue 审批帧")
    tool = str(approvals[-1].get("payload", {}).get("tool", ""))
    if tool != "add_to_analysis_queue":
        fail(f"审批工具不符预期: {tool}")
    frames2 = resume_approve(thread, tool)
    done = last_done(frames2)
    if not done:
        fail("approve 后缺少 done 帧")
    queue = done.get("payload", {}).get("analysis_queue") or []
    if not queue:
        fail("approve 后 analysis_queue 仍为空")
    ok(f"审批 approve 生效，analysis_queue={len(queue)} 项")

    # 4. 报告生成（管线步骤帧成对 + html_report 非空）
    frames = run_with_approvals(thread, "为分析队列里的活动生成分析报告")
    steps = {}
    for f in frames:
        if f.get("type") == "node_update" and f.get("node") in PIPELINE_STEPS:
            steps.setdefault(f["node"], set()).add(
                str(f.get("payload", {}).get("tool_status", "")))
    paired = sorted(s for s, st in steps.items() if {"running", "done"} <= st)
    if len(paired) < 3:
        fail(f"管线步骤 running/done 成对不足: {steps}")
    done = last_done(frames)
    if not done:
        fail("报告生成流中缺少 done 帧")
    if not done.get("payload", {}).get("html_report"):
        fail("done 帧 html_report 为空")
    ok(f"报告生成（{len(paired)} 个管线步骤帧成对，html_report 非空）")

    print("SMOKE-PASS")


if __name__ == "__main__":
    main()

# agent_v3 P4 离线打包实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 产出基于 openJiuwen 运行时的 ky10/x86_64 完整离线部署包，并在本机 Docker 容器内完成「断网安装 + 业务冒烟」验收。

**Architecture:** 全新建 `offline-v3/` 目录承载构建脚本、验证脚本、wheel 集与产物；旧 `offline-bundle/` 与 `scripts/build-offline-package.sh` 一字不动。构建在 `linux/amd64` Docker 容器内执行（`pip download --platform manylinux*` 保证 wheel 兼容性）；验证分两阶段——`--network none` 容器铁证闭包完备性，联网容器跑 API 级业务冒烟。

**Tech Stack:** bash、Docker（python:3.12-bookworm / debian:buster-slim）、pip download、httpx（冒烟脚本，容器内 venv 自带）。

**依据：** `docs/superpowers/specs/2026-08-12-agent-v3-p4-offline-packaging-design.md`

## Global Constraints

- 钉版（与 `backend/requirements.txt` 逐字一致）：`cryptography==46.0.7`、`openjiuwen==0.1.16.post2`
- pip download 平台参数固定为：`--only-binary=:all: --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 --python-version 312 --implementation cp --abi cp312`
- **禁止改动**：`offline-bundle/`、`scripts/build-offline-package.sh`、`deploy-offline.sh`、`backend/scripts/start-offline.sh`
- 唯一允许原地修改的既有文件：`backend/requirements-offline.txt`（补上述两行钉版）、`.gitignore`、文档
- 便携 Python 固定：`cpython-3.12.13-x86_64-linux-gnu.tar.gz`（python-build-standalone 20260623）
- 密钥纪律：LLM_API_KEY 只从 `backend/.env` 读出、经 `docker -e` 传入容器，不写入任何入库文件
- 本类任务为 bash/基建，TDD 以「先跑验证脚本看它失败 → 实现 → 再跑通过」形态落地；每个 Task 的验证步骤即其测试

---

### Task 1: requirements 对齐 + offline-v3 骨架

**Files:**
- Modify: `backend/requirements-offline.txt`
- Modify: `.gitignore`
- Create: `offline-v3/requirements.txt`
- Create: `offline-v3/wheels/.gitkeep`（目录占位；wheels 本身不入库）
- Create: `offline-v3/python/.gitkeep`、`offline-v3/dist/.gitkeep`

**Interfaces:**
- Produces: `offline-v3/requirements.txt`（build.sh 的 pip download 输入）；`backend/requirements-offline.txt` 与其内容完全一致（目标机 `start-offline.sh` 读取后者）

- [ ] **Step 1: 给 `backend/requirements-offline.txt` 补两行钉版**

在文件第 5 行（`python-multipart` 之后、空行注释区）插入，与 `backend/requirements.txt` 对应段逐字一致：

```
# agent_v3 (openJiuwen agent-core) — 精确钉版，0.x API 仍在演进
# cryptography 必须钉 46.0.7：PyPI 50.0.0 无 macOS x86_64 wheel 会触发源码编译（需 Rust）
cryptography==46.0.7
openjiuwen==0.1.16.post2
```

- [ ] **Step 2: 生成 `offline-v3/requirements.txt`**

内容与补完后的 `backend/requirements-offline.txt` 完全一致（单一事实来源，两文件保持同步）：

```bash
mkdir -p offline-v3/wheels offline-v3/python offline-v3/dist
cp backend/requirements-offline.txt offline-v3/requirements.txt
```

- [ ] **Step 3: 校验两文件一致 + 关键行存在**

```bash
diff backend/requirements-offline.txt offline-v3/requirements.txt && echo IDENTICAL
grep -n "openjiuwen==0.1.16.post2\|cryptography==46.0.7" backend/requirements-offline.txt
```

预期：`IDENTICAL` + 两行钉版各命中一次。

- [ ] **Step 4: 拷贝便携 Python 缓存（避免重复下载）**

```bash
cp offline-bundle/python/cpython-3.12.13-x86_64-linux-gnu.tar.gz offline-v3/python/
gzip -t offline-v3/python/cpython-3.12.13-x86_64-linux-gnu.tar.gz && echo ARCHIVE_OK
```

- [ ] **Step 5: .gitignore 排除大文件目录**

在 `.gitignore` 追加：

```
# P4 离线包（大文件不入库）
offline-v3/wheels/*.whl
offline-v3/python/*.tar.gz
offline-v3/dist/
```

- [ ] **Step 6: Commit**

```bash
git add backend/requirements-offline.txt offline-v3/requirements.txt .gitignore offline-v3
git commit -m "chore(agent_v3): P4 requirements-offline 补 openjiuwen/cryptography 钉版 + offline-v3 骨架"
```

---

### Task 2: 编写 offline-v3/build.sh

**Files:**
- Create: `offline-v3/build.sh`

**Interfaces:**
- Consumes: `offline-v3/requirements.txt`（Task 1）、`offline-v3/python/` 缓存（Task 1）、`frontend/dist/index.html`（宿主机预先 npm build）
- Produces: `offline-v3/dist/activity-analysis-assistant-offline-<yyyymmdd-hhmmss>.tar.gz`；产物内部布局 `activity-analysis-assistant/{backend,ops,data,offline-bundle,deploy-offline.sh}`（verify.sh 依赖此布局）

- [ ] **Step 1: 写 build.sh 全文**

```bash
#!/usr/bin/env bash
#
# openJiuwen 版离线部署包构建（麒麟 V10 / Linux x86_64 / Python 3.12）
# 宿主机（macOS）用法：
#   cd frontend && npm ci && npm run build
#   docker run --rm --platform linux/amd64 -v "$PWD":/workspace -w /workspace \
#     python:3.12-bookworm bash offline-v3/build.sh
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
V3_DIR="$ROOT_DIR/offline-v3"
BUILD_PYTHON="${BUILD_PYTHON:-python3.12}"
PYTHON_ARCHIVE_NAME="cpython-3.12.13-x86_64-linux-gnu.tar.gz"
PYTHON_ARCHIVE_URL="${PYTHON_ARCHIVE_URL:-https://github.com/astral-sh/python-build-standalone/releases/download/20260623/cpython-3.12.13%2B20260623-x86_64-unknown-linux-gnu-install_only.tar.gz}"
PACKAGE_NAME="${PACKAGE_NAME:-activity-analysis-assistant-offline-$(date +%Y%m%d-%H%M%S).tar.gz}"
DIST_DIR="$V3_DIR/dist"
PACKAGE_PATH="$DIST_DIR/$PACKAGE_NAME"
BUILD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/activity-analysis-offline-v3-build.XXXXXX")"
STAGE_DIR="$BUILD_ROOT/activity-analysis-assistant"
BUILD_VENV="$BUILD_ROOT/build-venv"

cleanup() { rm -rf "$BUILD_ROOT"; }
trap cleanup EXIT

fail() { echo "错误: $*" >&2; exit 1; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "缺少命令: $1"; }

[ "$(uname -s)" = "Linux" ] || fail "必须在 Linux x86_64（或 linux/amd64 容器）执行"
[ "$(uname -m)" = "x86_64" ] || fail "构建机架构必须是 x86_64"
require_command "$BUILD_PYTHON"
require_command tar
require_command sha256sum
require_command gzip
require_command xargs

echo ">>> [1/5] 校验前端产物（本脚本不构建前端，请先在宿主机 npm run build）"
[ -f "$ROOT_DIR/frontend/dist/index.html" ] || \
    fail "缺少 frontend/dist/index.html，请先在宿主机执行: cd frontend && npm ci && npm run build"

echo ">>> [2/5] 准备部署目录"
mkdir -p "$STAGE_DIR" "$DIST_DIR" "$V3_DIR/wheels" "$V3_DIR/python"
tar -C "$ROOT_DIR" \
    --exclude='backend/venv' --exclude='backend/.env' --exclude='backend/data' \
    --exclude='backend/src/static' --exclude='*/__pycache__' \
    -cf - backend | tar -C "$STAGE_DIR" -xf -
tar -C "$ROOT_DIR" \
    --exclude='ops/data' --exclude='ops/.env' --exclude='*/__pycache__' \
    -cf - ops | tar -C "$STAGE_DIR" -xf -
mkdir -p "$STAGE_DIR/data"
cp -a "$ROOT_DIR/data/mysql" "$STAGE_DIR/data/mysql"
cp -a "$ROOT_DIR/frontend/dist" "$STAGE_DIR/backend/src/static"
cp "$ROOT_DIR/deploy-offline.sh" "$STAGE_DIR/deploy-offline.sh"
mkdir -p "$STAGE_DIR/offline-bundle/python" "$STAGE_DIR/offline-bundle/wheels"

echo ">>> [3/5] 准备便携 Python"
PYTHON_ARCHIVE_TARGET="$STAGE_DIR/offline-bundle/python/$PYTHON_ARCHIVE_NAME"
if [ -f "$V3_DIR/python/$PYTHON_ARCHIVE_NAME" ]; then
    cp "$V3_DIR/python/$PYTHON_ARCHIVE_NAME" "$PYTHON_ARCHIVE_TARGET"
elif [ -f "$ROOT_DIR/offline-bundle/python/$PYTHON_ARCHIVE_NAME" ]; then
    cp "$ROOT_DIR/offline-bundle/python/$PYTHON_ARCHIVE_NAME" "$PYTHON_ARCHIVE_TARGET"
    cp "$ROOT_DIR/offline-bundle/python/$PYTHON_ARCHIVE_NAME" "$V3_DIR/python/"
else
    require_command curl
    curl -fL --retry 3 -o "$PYTHON_ARCHIVE_TARGET" "$PYTHON_ARCHIVE_URL"
    cp "$PYTHON_ARCHIVE_TARGET" "$V3_DIR/python/"
fi
gzip -t "$PYTHON_ARCHIVE_TARGET"

echo ">>> [4/5] 下载全部 Python 离线依赖（openJiuwen 全量闭包）"
"$BUILD_PYTHON" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install --upgrade pip
# pip download 会跳过 dest 中已存在的同名文件，offline-v3/wheels 兼作本机缓存
"$BUILD_VENV/bin/python" -m pip download \
    --only-binary=:all: \
    --platform manylinux2014_x86_64 \
    --platform manylinux_2_17_x86_64 \
    --platform manylinux_2_28_x86_64 \
    --python-version 312 \
    --implementation cp \
    --abi cp312 \
    --dest "$V3_DIR/wheels" \
    -r "$V3_DIR/requirements.txt"
cp -a "$V3_DIR/wheels/." "$STAGE_DIR/offline-bundle/wheels/"

echo ">>> [5/5] 生成校验清单并打包"
(
    cd "$STAGE_DIR/offline-bundle"
    find python wheels -type f -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256
)
chmod +x "$STAGE_DIR/deploy-offline.sh" "$STAGE_DIR/backend/scripts/"*.sh
tar -C "$BUILD_ROOT" -czf "$PACKAGE_PATH" activity-analysis-assistant

echo ""
echo "离线部署包已生成: $PACKAGE_PATH"
echo "wheels: $(ls "$V3_DIR"/wheels/*.whl | wc -l | tr -d ' ') 个，$(du -sh "$V3_DIR/wheels" | cut -f1)"
echo "目标机只需解压后执行一次: bash deploy-offline.sh"
```

- [ ] **Step 2: 语法检查 + 可执行位**

```bash
bash -n offline-v3/build.sh && echo SYNTAX_OK
chmod +x offline-v3/build.sh
```

- [ ] **Step 3: 静态比对旧脚本语义**

```bash
diff <(grep -v '^#' scripts/build-offline-package.sh | grep -oE '(cp -a|tar|pip download|sha256sum|MANIFEST)' | sort -u) \
     <(grep -v '^#' offline-v3/build.sh | grep -oE '(cp -a|tar|pip download|sha256sum|MANIFEST)' | sort -u)
```

预期：关键操作集合一致（npm 相关除外，新脚本无 npm 步骤）。

- [ ] **Step 4: Commit**

```bash
git add offline-v3/build.sh
git commit -m "feat(agent_v3): P4 offline-v3/build.sh——openJiuwen 版离线包构建脚本（Docker 容器内执行）"
```

---

### Task 3: 首次 Docker 构建（实测闭包，逐案处理缺 wheel 依赖）

**Files:**
- Modify: `offline-v3/requirements.txt`（仅当实测发现无 wheel 依赖需钉版例外时）
- Modify: `offline-v3/build.sh`（仅当实测发现脚本问题时）
- 记录用草稿：`findings.md` 或终端日志（最终汇入 Task 6 验收文档）

**Interfaces:**
- Consumes: Task 2 的 `offline-v3/build.sh`
- Produces: `offline-v3/dist/activity-analysis-assistant-offline-*.tar.gz`（verify.sh 的输入）；闭包体积与 wheel 数量记录

- [ ] **Step 1: 宿主机前端构建**

```bash
cd frontend && npm ci && npm run build && ls dist/index.html
```

预期：`dist/index.html` 存在。（若 frontend/dist 已是最新可跳过，但首次执行必须跑一次确认。）

- [ ] **Step 2: 宿主机预拉镜像 + 启动 mock 之外的准备工作**

```bash
docker pull --platform linux/amd64 python:3.12-bookworm
```

- [ ] **Step 3: 执行构建（预期首次耗时 10-30 分钟，主要在网络下载）**

```bash
docker run --rm --platform linux/amd64 -v "$PWD":/workspace -w /workspace \
  python:3.12-bookworm bash offline-v3/build.sh
```

预期：尾部输出 `离线部署包已生成: ...` + wheels 数量/体积。

**若 `pip download` 因某包无 manylinux cp312 wheel 失败**（`--only-binary=:all:` 硬失败，报错形如 `ERROR: Could not find a version that satisfies the requirement <pkg>`）：
1. 记录包名与来源依赖链（`pip download` 报错上下文会指出父依赖）；
2. 优先为该传递依赖在 `offline-v3/requirements.txt` 追加一行钉版例外（选一个提供 manylinux cp312 wheel 的兼容版本，注释注明原因）；
3. 同步追加到 `backend/requirements-offline.txt`（两文件保持逐字一致）；
4. 重跑本步骤。逐案记录（包名/选择版本/原因），汇入 Task 6 验收文档。

- [ ] **Step 4: 闭包完备性静态检查**

```bash
# ops-assistant 复用主 venv，其依赖必须被闭包覆盖（httpx 由 openai 带入；pyyaml 需确认）
ls offline-v3/wheels/ | grep -i "pyyaml\|PyYAML" || echo "MISSING_PYYAML"
ls offline-v3/wheels/ | grep -ci "httpx"
ls offline-v3/wheels/*.whl | wc -l
du -sh offline-v3/wheels
```

预期：pyyaml wheel 存在（若 `MISSING_PYYAML`：在两份 requirements 追加 `pyyaml>=6.0` 并重跑 Step 3）；httpx ≥1；记录 wheels 总数与总体积。

- [ ] **Step 5: 产物完整性自检**

```bash
PKG=$(ls -t offline-v3/dist/activity-analysis-assistant-offline-*.tar.gz | head -1)
tar -tzf "$PKG" | grep -c "\.whl$"
tar -tzf "$PKG" | grep -E "offline-bundle/(MANIFEST.sha256|python/cpython)|backend/src/static/index.html|deploy-offline.sh"
```

预期：whl 数与 Step 4 一致；4 个关键路径各命中。

- [ ] **Step 6: Commit（仅脚本/requirements 变更；产物不入库）**

```bash
git add offline-v3/requirements.txt offline-v3/build.sh backend/requirements-offline.txt
git commit -m "fix(agent_v3): P4 构建实测修正——<填入实际个案，无则写‘闭包一次通过，无钉版例外’>"
```

---

### Task 4: 编写 offline-v3/verify.sh + offline-v3/smoke.py

**Files:**
- Create: `offline-v3/verify.sh`
- Create: `offline-v3/smoke.py`

**Interfaces:**
- Consumes: Task 3 产物 tar.gz；宿主机 `backend/.env`（仅读 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL 三个键）；宿主机 mock 服务 :8005
- Produces: 两阶段验证的终端证据（阶段1 `IMPORT_OK: src.main`；阶段2 `SMOKE-PASS`）

冒烟依赖的 API 契约（已核实，勿改）：
- `POST /api/v2/agent/run` body `{thread_id, message, original_user_text, user_id, org_no, channel}` → SSE，裸 `data: {json}\n\n`
- `POST /api/v2/agent/resume` body `{thread_id, decision, tool, user_id, org_no, channel}` → SSE
- 帧：`{"type":"approval_required","payload":{"tool","args",...}}`；`{"type":"node_update","node":<工具或管线步骤名>,"payload":{"tool_status":"running"|"done"}}`；`{"type":"done","payload":{"awaiting_approval","analysis_queue","html_report","final_response",...}}`
- `GET /health` → 200

- [ ] **Step 1: 写 offline-v3/smoke.py 全文**

```python
"""P4 离线包业务冒烟：健康检查 → 对话(查询工具) → 审批 approve → 报告生成。

容器内执行（venv python，httpx 由 openai 传递依赖提供）：
    backend/venv/bin/python /smoke.py
退出码 0 = 全部通过；任一断言失败即非零退出。
"""
import json
import sys
import uuid

import httpx

BASE = "http://127.0.0.1:8000"
USER_ID = "p4smoke"
PIPELINE_STEPS = {
    "selected_activity_router", "outbound_activity_data_fetch", "template_list_fetch",
    "template_matching", "component_value_fetch", "component_value_cleanup",
    "activity_template_matching", "uploaded_component_value_extract",
    "marketing_report_synthesis",
}
TIMEOUT = httpx.Timeout(900.0, connect=10.0)


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
    return _post_stream("/api/v2/agent/run", {
        "thread_id": thread_id, "message": message, "original_user_text": message,
        "user_id": USER_ID, "org_no": "001", "channel": "AILMIS",
    })


def resume_approve(thread_id: str, tool: str) -> list:
    return _post_stream("/api/v2/agent/resume", {
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
    resp = httpx.get(f"{BASE}/health", timeout=10.0)
    if resp.status_code != 200:
        fail(f"/health HTTP {resp.status_code}")
    ok("健康检查")

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
    if not done.get("payload", {}).get("html_report"):
        fail("done 帧 html_report 为空")
    ok(f"报告生成（{len(paired)} 个管线步骤帧成对，html_report 非空）")

    print("SMOKE-PASS")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 写 offline-v3/verify.sh 全文**

```bash
#!/usr/bin/env bash
#
# P4 离线部署包两阶段验证（本机 Docker，macOS 可跑）
# 用法: bash offline-v3/verify.sh [包路径]   # 缺省取 offline-v3/dist/ 最新产物
# 前置: 宿主机 mock 营销接口已起 (:8005)；backend/.env 含有效 LLM_* 配置
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
V3_DIR="$ROOT_DIR/offline-v3"
PKG="${1:-$(ls -t "$V3_DIR"/dist/activity-analysis-assistant-offline-*.tar.gz 2>/dev/null | head -1)}"
[ -n "$PKG" ] && [ -f "$PKG" ] || { echo "错误: 未找到部署包（$PKG）" >&2; exit 1; }
echo "验证目标: $PKG"

echo ""
echo ">>> 阶段 1/2: 断网离线安装验证 (debian:buster-slim, --network none)"
docker run --rm --platform linux/amd64 --network none \
    -v "$PKG":/pkg/package.tar.gz:ro \
    debian:buster-slim bash -s <<'STAGE1'
set -euo pipefail
cd /tmp
tar -xzf /pkg/package.tar.gz
cd activity-analysis-assistant
( cd offline-bundle && sha256sum -c MANIFEST.sha256 --quiet )
echo "MANIFEST 校验通过"
printf 'LLM_BASE_URL=http://placeholder.invalid/v1\nLLM_MODEL=placeholder\n' > backend/.env
tar -xzf offline-bundle/python/cpython-*.tar.gz -C offline-bundle/python
offline-bundle/python/python/bin/python3 -m venv backend/venv
backend/venv/bin/pip install --no-index --find-links=offline-bundle/wheels \
    -r backend/requirements-offline.txt
cd backend
./venv/bin/python -c "import src.main; print('IMPORT_OK: src.main')"
STAGE1
echo "阶段 1 通过: MANIFEST + 断网安装 + import src.main"

echo ""
echo ">>> 阶段 2/2: 业务冒烟 (联网容器 + 宿主机 mock:8005)"
ENV_FILE="$ROOT_DIR/backend/.env"
[ -f "$ENV_FILE" ] || { echo "错误: 缺少 $ENV_FILE" >&2; exit 1; }
LLM_BASE_URL="$(grep -E '^LLM_BASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
LLM_API_KEY="$(grep -E '^LLM_API_KEY=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
LLM_MODEL="$(grep -E '^LLM_MODEL=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
[ -n "$LLM_BASE_URL" ] && [ -n "$LLM_MODEL" ] || { echo "错误: backend/.env 缺少 LLM_BASE_URL/LLM_MODEL" >&2; exit 1; }
curl -sf -o /dev/null --max-time 3 http://localhost:8005/docs \
    || { echo "错误: 宿主机 mock :8005 未启动，请先: backend/venv/bin/python mock/app.py" >&2; exit 1; }

docker run --rm --platform linux/amd64 \
    -e LLM_BASE_URL -e LLM_API_KEY -e LLM_MODEL \
    -v "$PKG":/pkg/package.tar.gz:ro \
    -v "$V3_DIR/smoke.py":/smoke.py:ro \
    debian:buster-slim bash -s <<'STAGE2'
set -euo pipefail
cd /tmp
tar -xzf /pkg/package.tar.gz
cd activity-analysis-assistant
cat > backend/.env <<EOF
LLM_BASE_URL=$LLM_BASE_URL
LLM_API_KEY=$LLM_API_KEY
LLM_MODEL=$LLM_MODEL
LLM_TIMEOUT_SECONDS=1200
BANK_MARKETING_ACTIVITY_LIST_URL=http://host.docker.internal:8005/api2/campaigns/search
BANK_MARKETING_TEMPLATE_LIST_URL=http://host.docker.internal:8005/api2/templates
BANK_MARKETING_COMPONENT_VALUES_URL=http://host.docker.internal:8005/api2/component-values
BANK_MARKETING_OUTBOUND_ACTIVITY_DATA_URL=http://host.docker.internal:8005/api2/dataservice/query/{trade_code}
EOF
export INPUT_START_OPS=n
nohup bash deploy-offline.sh </dev/null >/tmp/deploy.log 2>&1 &
READY=0
for _ in $(seq 1 120); do
    if backend/venv/bin/python -c \
        "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status==200 else 1)" \
        2>/dev/null; then
        READY=1; break
    fi
    sleep 5
done
if [ "$READY" != "1" ]; then
    echo "错误: 服务 10 分钟内未就绪，deploy.log 尾部:" >&2
    tail -50 /tmp/deploy.log >&2
    exit 1
fi
echo "服务已就绪，开始冒烟"
backend/venv/bin/python /smoke.py
STAGE2
echo "阶段 2 通过: 部署 + 启动 + 业务冒烟"
echo ""
echo "VERIFY-PASS: $PKG"
```

注意：内层 `cat > backend/.env <<EOF` 故意不引用 EOF（容器内展开 `$LLM_*` 环境变量）；外层 `<<'STAGE2'` 引用防止宿主机提前展开。`{trade_code}` 字面量原样写入。

- [ ] **Step 3: 语法检查 + 可执行位**

```bash
bash -n offline-v3/verify.sh && echo VERIFY_SYNTAX_OK
backend/venv/bin/python -m py_compile offline-v3/smoke.py && echo SMOKE_COMPILE_OK
chmod +x offline-v3/verify.sh
```

- [ ] **Step 4: Commit**

```bash
git add offline-v3/verify.sh offline-v3/smoke.py
git commit -m "feat(agent_v3): P4 offline-v3/verify.sh+smoke.py——断网安装+业务冒烟两阶段验证"
```

---

### Task 5: 执行两阶段验证

**Files:**
- 无新建；证据收集到终端日志（汇入 Task 6 验收文档）

**Interfaces:**
- Consumes: Task 3 产物、Task 4 脚本
- Produces: 阶段1/阶段2 通过证据（逐条记录：MANIFEST、IMPORT_OK、SMOKE-OK×4、SMOKE-PASS）

- [ ] **Step 1: 预拉镜像 + 启动宿主机 mock**

```bash
docker pull --platform linux/amd64 debian:buster-slim
curl -sf -o /dev/null --max-time 3 http://localhost:8005/docs || \
  (nohup backend/venv/bin/python mock/app.py >/tmp/p4-mock.log 2>&1 & sleep 3)
curl -sf -o /dev/null http://localhost:8005/docs && echo MOCK_OK
```

- [ ] **Step 2: 跑 verify.sh（全程预期 10-25 分钟；报告生成冒烟单步约 2-3 分钟）**

```bash
bash offline-v3/verify.sh 2>&1 | tee /tmp/p4-verify.log
```

预期终态输出：`VERIFY-PASS: <包路径>`。

**常见失败处置**（逐案记录到 /tmp/p4-verify.log 尾部，供 Task 6 引用）：
- 阶段1 pip 报 `No matching distribution`：闭包缺包/缺平台 wheel → 回 Task 3 Step 3 的个案流程，补钉版后重出包再验；
- 阶段1 `import src.main` 失败且报错为配置项（非 ModuleNotFound）：记录并调整阶段1最小 `.env` 补对应键；为 ModuleNotFound 则是闭包问题，同上回 Task 3；
- 阶段2 服务未就绪：`tail deploy.log`；若是 `AGENT_V3_ENABLED` 残留类 pydantic 校验错误，检查写入的 `.env` 键（本脚本不写入该键，理论上不会发生）；
- 阶段2 容器访问不到 mock：确认 Docker Desktop 的 `host.docker.internal` 可用（macOS 内置）；不行则在 docker run 追加 `--add-host host.docker.internal:host-gateway` 重试；
- 阶段2 LLM 不可达/超时：确认宿主机网络可达 LLM 端点；代理环境下给容器加 `-e HTTPS_PROXY=...`。

- [ ] **Step 3: 提取证据清单**

```bash
grep -E "MANIFEST 校验通过|IMPORT_OK|SMOKE-OK|SMOKE-FAIL|SMOKE-PASS|VERIFY-PASS" /tmp/p4-verify.log
```

预期：MANIFEST×1、IMPORT_OK×1、SMOKE-OK×4、SMOKE-PASS×1、VERIFY-PASS×1，无 SMOKE-FAIL。

---

### Task 6: 部署文档新章节 + P4 验收记录

**Files:**
- Modify: `DEPLOY-OFFLINE-KYLIN.md`（新增章节，旧内容一字不动）
- Create: `docs/superpowers/specs/2026-08-12-agent-v3-p4-acceptance.md`

**Interfaces:**
- Consumes: Task 3 的闭包记录（wheel 数/体积/钉版例外）、Task 5 证据清单

- [ ] **Step 1: DEPLOY-OFFLINE-KYLIN.md 新增章节**

在文件第 1 行标题之后、现有 `> 适用目标机` 引言块之前插入：

```markdown
> **【openJiuwen 版（agent_v3）部署请看这里】** 2026-08-12 起运行时迁移至 openJiuwen
> agent-core（v3 为唯一运行时）。新离线包由 `offline-v3/` 构建与验证，见本文
> [第 0 章](#0-openjiuwen-版agent_v3离线部署p4)。下文第 1-9 章为 langchain 时代
> 旧版流程，仅作历史归档保留。

---

## 0. openJiuwen 版（agent_v3）离线部署（P4）

### 0.1 与旧版差异

| 项 | 旧版（langchain） | 新版（openJiuwen v3） |
|---|---|---|
| 构建脚本 | `scripts/build-offline-package.sh`（需 Linux 构建机） | `offline-v3/build.sh`（本机 Docker，linux/amd64） |
| wheel 集 | `offline-bundle/wheels`（langchain 系，已归档） | `offline-v3/wheels`（openJiuwen 全量闭包） |
| 构建验证 | 无 | `offline-v3/verify.sh`（断网安装 + 业务冒烟） |
| 目标机部署 | `bash deploy-offline.sh` | **不变** |

目标机侧部署步骤与第 5 章完全一致（产物内部布局未变），仅两点注意：

1. **`.env` 若从旧版环境拷贝，必须删除 `AGENT_V3_ENABLED` 键**——该键已随 v3 成为
   唯一运行时而移除，残留会导致 pydantic-settings ValidationError 启动失败。
2. `data/checkpoints.db`（v2 langgraph checkpoint）为历史文件，新版不读写，可归档保留。

### 0.2 构建（本机 macOS + Docker）

```bash
cd frontend && npm ci && npm run build && cd ..
docker run --rm --platform linux/amd64 -v "$PWD":/workspace -w /workspace \
  python:3.12-bookworm bash offline-v3/build.sh
# 产物: offline-v3/dist/activity-analysis-assistant-offline-<时间戳>.tar.gz
```

### 0.3 构建后验证（可选但强烈建议）

```bash
# 前置: 宿主机起 mock（backend/venv/bin/python mock/app.py），backend/.env 配好 LLM
bash offline-v3/verify.sh
# 通过标准: 输出 VERIFY-PASS（阶段1=断网安装铁证闭包完备；阶段2=对话/审批/报告冒烟）
```

### 0.4 目标机部署

与第 5 章一致：拷贝 tar.gz 到目标机 → `tar -xzf` → `bash deploy-offline.sh`，
按提示填写内网 LLM 与银行营销接口地址。
```

- [ ] **Step 2: 写 P4 验收记录 `docs/superpowers/specs/2026-08-12-agent-v3-p4-acceptance.md`**

模板（尖括号处用 Task 3/5 实测数据填充，不允许留空）：

```markdown
# agent_v3 P4 验收记录：openJiuwen 版离线部署包

> 日期：2026-08-12
> 依据：`2026-08-12-agent-v3-p4-offline-packaging-design.md`
> 环境：macOS 宿主机 + Docker linux/amd64（构建 python:3.12-bookworm；验证 debian:buster-slim glibc 2.28 ≈ ky10 V10）
> 结论：<通过 / 附条件通过>

## 产物

- 包：`offline-v3/dist/activity-analysis-assistant-offline-<时间戳>.tar.gz`（<大小>）
- wheel 集：<N> 个 / <体积>；MANIFEST.sha256 随包
- 钉版例外（无 wheel 个案处理）：<逐条：包名/版本/原因；无则写"无">

## 阶段 1：断网安装验证（--network none）

| 检查 | 结果 |
|---|---|
| MANIFEST.sha256 | <✅> |
| pip --no-index 全量安装 | <✅> |
| import src.main | <✅ IMPORT_OK> |

## 阶段 2：业务冒烟

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 健康检查 + deploy-offline.sh 无交互跑通 | <> | |
| 2 | 对话 + search_activities | <> | SMOKE-OK |
| 3 | 审批 approve（add_to_analysis_queue） | <> | analysis_queue=N |
| 4 | generate_report 全流程 | <> | <M> 个管线步骤帧成对，html_report 非空 |

## 部署警告（随版本发布）

1. 旧 `.env` 残留 `AGENT_V3_ENABLED` 会导致启动失败，部署前删除（沿用 P3 警告）。
2. ~~requirements-offline.txt 未包含 openjiuwen~~（P3 警告 #2，本阶段已闭环）。
```

- [ ] **Step 3: Commit**

```bash
git add DEPLOY-OFFLINE-KYLIN.md docs/superpowers/specs/2026-08-12-agent-v3-p4-acceptance.md
git commit -m "docs(agent_v3): P4 验收记录 + DEPLOY-OFFLINE-KYLIN 新增 openJiuwen 版部署章节"
```

---

## Self-Review 结论

- **Spec 覆盖**：设计 §2 目录/文件 → Task 1；§3 构建链路 → Task 2/3；§4 两阶段验证 → Task 4/5；§5 文档与交付 → Task 6；§6 不做项已列入 Global Constraints 禁止改动清单。设计提到"验收通过后关闭 P3 警告 #2" → Task 6 Step 2 模板第 2 条。
- **Placeholder 扫描**：验收文档模板中的 `<>` 为实测数据占位（执行时填充），属有意设计；脚本全文无 TODO。
- **类型/契约一致性**：smoke.py 的 API 路径/帧类型/字段名与 `backend/src/api/routers/agent_v2.py`、`agent_v3/events/_frames.py`、`sse_bridge.py` 逐一核对一致；verify.sh 的 `SMOKE-PASS`/`IMPORT_OK` 与 smoke.py/阶段1 heredoc 输出一致；build.sh 产物内部布局（`offline-bundle/` + `deploy-offline.sh`）与 verify.sh 解压假设一致。

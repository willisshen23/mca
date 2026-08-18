# 外呼活动多活动合并查询 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 智能体一次合并调用查询多个活动的外呼数据（`edw_act_no` 传 `A','B','C` 格式），失败回退逐活动探测；mock 支持多值解析并补充多活动数据。

**Architecture:** 多值拼接收敛在 client（`A','B','C`，首尾引号由服务端补全）；agent 的 `_probe_outbound_activities` 改为合并探测 + 按 `matched_act_nos` 逐活动判定 + 按 act_no 拆分 data，异常/失败/响应缺 `matched_act_nos` 时回退现有逐活动探测；mock 按 `','` 拆分解析（兼容三种形态），多记录合行后统一过滤分页。

**Tech Stack:** Python 3.10+、FastAPI（mock）、openpyxl（Excel 数据）、pytest。

**Spec:** `docs/superpowers/specs/2026-07-29-outbound-multi-activity-design.md`

## Global Constraints

- `edw_act_no` 多值格式：`A','B','C`（值内含中间引号，**不带首尾引号**，服务端补全）；单值为裸值 `A`。
- mock 解析必须兼容三种形态：`A`、`A','B','C`、`'A','B','C'`。
- 查不到的活动不产出行（模拟真实 SQL IN 查询语义），这是 agent 判定 not_found 的依据。
- ruff：line-length 100，target py310。
- 测试不得访问网络/LLM；backend 测试在 `backend/` 目录下运行（`from src...` 导入），mock 测试在仓库根目录运行。
- 提交信息使用中文，结尾带 `Co-Authored-By: Claude <noreply@anthropic.com>`。

---

### Task 1: mock Excel 补充 2 条活动数据

**Files:**
- Modify: `mock/外呼活动 mock 数据.xlsx`（二进制，用脚本改）
- 脚本: `/tmp/add_mock_activities.py`（一次性，不进仓库）

**Interfaces:**
- Produces: Excel 中存在 3 条活动：`ACT20260116906568`（原有）、`ACT20260116906569`、`ACT20260116906570`。每条含 `_COLUMN_MAP` 全部 14 列；各文本块内的 `act_no` 与新编号一致；`act_name` 分别带 B/C 后缀；外呼人数数值有区分（+1000/+2000）。Task 2 的集成测试依赖这三个编号。

- [ ] **Step 1: 查看现有数据结构**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis
python -c "
import openpyxl
wb = openpyxl.load_workbook('mock/外呼活动 mock 数据.xlsx')
ws = wb.active
print('max_row:', ws.max_row, 'max_col:', ws.max_column)
print('headers:', [c.value for c in ws[1]])
print('act_no cell:', ws.cell(2, 1).value)
"
```
Expected: 输出列头 14 列、第 2 行 act_no 为 `ACT20260116906568`。若列数/结构不符，停下来核对 `mock/waihu_data_service.py` 的 `_COLUMN_MAP`。

- [ ] **Step 2: 写补充脚本**

Create `/tmp/add_mock_activities.py`:

```python
"""一次性脚本：往外呼 mock Excel 追加 2 条活动（复制第 2 行，改编号/名称/外呼人数）。"""
from __future__ import annotations

import re
from pathlib import Path

import openpyxl

PATH = Path("/Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis/mock/外呼活动 mock 数据.xlsx")
SRC_ROW = 2
SRC_ACT_NO = "ACT20260116906568"
NEW_ACTS = [
    ("ACT20260116906569", "B", 1000),
    ("ACT20260116906570", "C", 2000),
]


def transform(text: str, new_act_no: str, suffix: str, delta: int) -> str:
    text = text.replace(SRC_ACT_NO, new_act_no)
    # act_name 加后缀，便于区分
    text = re.sub(
        r'("act_name"\s*:\s*")([^"]*)(")',
        lambda m: m.group(1) + m.group(2) + suffix + m.group(3),
        text,
    )
    # 外呼人数 +delta，便于区分
    text = re.sub(
        r'("外呼人数"\s*:\s*)(\d+)',
        lambda m: m.group(1) + str(int(m.group(2)) + delta),
        text,
        count=1,
    )
    return text


def main() -> None:
    wb = openpyxl.load_workbook(PATH)
    ws = wb.active
    existing = {ws.cell(r, 1).value for r in range(2, ws.max_row + 1)}
    next_row = ws.max_row + 1
    for new_act_no, suffix, delta in NEW_ACTS:
        if new_act_no in existing:
            print(f"skip {new_act_no}（已存在）")
            continue
        for col in range(1, ws.max_column + 1):
            value = ws.cell(SRC_ROW, col).value
            if col == 1:
                ws.cell(next_row, col).value = new_act_no
            elif isinstance(value, str):
                ws.cell(next_row, col).value = transform(value, new_act_no, suffix, delta)
            else:
                ws.cell(next_row, col).value = value
        print(f"added {new_act_no} at row {next_row}")
        next_row += 1
    wb.save(PATH)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 运行脚本并验证**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis
python /tmp/add_mock_activities.py
python -c "
import sys; sys.path.insert(0, 'mock')
import waihu_data_service as ds
recs = ds.load_data()
print([r['act_no'] for r in recs])
for r in recs:
    print(r['act_no'], '|', (r.get('basic_info') or {}).get('act_name'), '|', (r.get('execution') or {}).get('外呼人数'))
"
```
Expected: 3 条记录，act_no 分别为 568/569/570，act_name 带 B/C 后缀，外呼人数依次递增；每条记录 `basic_info` 内 `act_no` 与外层一致。

- [ ] **Step 4: Commit**

```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis
git add "mock/外呼活动 mock 数据.xlsx"
git commit -m "mock：外呼活动数据补充 2 条活动，支撑多活动场景

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: mock 多值解析与多活动合并返回

**Files:**
- Modify: `mock/waihu_data_service.py:147-153`（新增 `get_activities_by_ids`，保留 `get_activity_by_id`）
- Modify: `mock/outbound_api2_router.py:11-14,161-231`（多值解析 + 合行后统一过滤）
- Test: `mock/tests/test_outbound_api2_router.py`（新建）

**Interfaces:**
- Consumes: Task 1 的 Excel 三个活动编号（仅集成测试用）。
- Produces:
  - `waihu_data_service.get_activities_by_ids(act_nos: list[str]) -> dict[str, dict]`：返回 `{act_no: record}`，未命中编号不出现。
  - `outbound_api2_router._split_act_nos(value: Any) -> list[str]`：解析单值/多值/list。
  - `outbound_api2_router._extract_act_nos(body: dict) -> list[str]]`（取代 `_extract_act_no`，后者删除）。
  - `outbound_api2_router._build_rows_for_record(api_key: str, record: dict) -> list[dict]`（取代 `_build_rows`，不再过滤分页）。
  - `_query_outbound_data` 行为：多活动合行后统一 `_filter_rows`；未命中活动不产出行。

- [ ] **Step 1: 写失败测试**

Create `mock/tests/test_outbound_api2_router.py`:

```python
"""外呼 api2 mock 多活动解析与合并返回测试。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import outbound_api2_router as router  # noqa: E402
import waihu_data_service as data_service  # noqa: E402


def _record(act_no: str, act_name: str) -> dict:
    return {
        "act_no": act_no,
        "basic_info": {
            "act_no": act_no,
            "act_name": act_name,
            "活动状态": "执行中",
            "活动开始时间": "2026-01-01",
        },
        "execution": {"act_no": act_no, "act_name": act_name, "外呼人数": 100},
    }


def test_split_act_nos_single():
    assert router._split_act_nos("A") == ["A"]


def test_split_act_nos_multi_without_outer_quotes():
    assert router._split_act_nos("A','B','C") == ["A", "B", "C"]


def test_split_act_nos_multi_with_outer_quotes():
    assert router._split_act_nos("'A','B','C'") == ["A", "B", "C"]


def test_split_act_nos_list_passthrough_dedup():
    assert router._split_act_nos(["A", "B", "A", " "]) == ["A", "B"]


def test_extract_act_nos_from_pms():
    body = {"pms": {"edw_act_no": "A','B"}}
    assert router._extract_act_nos(body) == ["A", "B"]


def test_get_activities_by_ids(monkeypatch):
    monkeypatch.setattr(
        data_service, "load_data", lambda: [_record("A", "甲"), _record("B", "乙")]
    )
    assert set(data_service.get_activities_by_ids(["A", "B", "C"])) == {"A", "B"}
    assert data_service.get_activities_by_ids([]) == {}


def test_query_multi_activity_merges_rows(monkeypatch):
    records = {"A": _record("A", "甲"), "B": _record("B", "乙")}
    monkeypatch.setattr(
        router,
        "get_activities_by_ids",
        lambda act_nos: {a: records[a] for a in act_nos if a in records},
    )
    body = {"pms": {"edw_act_no": "A','B"}, "props": {"limit": 20, "start": 1}}
    resp = router._query_outbound_data("EDW_RTL_MED_ACTIVITY_BASE_INFO", body)
    assert resp["retCode"] == "000000"
    assert [row["act_no"] for row in resp["result"]] == ["A", "B"]


def test_query_multi_activity_skips_missing(monkeypatch):
    records = {"A": _record("A", "甲")}
    monkeypatch.setattr(
        router,
        "get_activities_by_ids",
        lambda act_nos: {a: records[a] for a in act_nos if a in records},
    )
    body = {"pms": {"edw_act_no": "A','MISSING"}}
    resp = router._query_outbound_data("EDW_RTL_MED_ACTIVITY_BASE_INFO", body)
    assert [row["act_no"] for row in resp["result"]] == ["A"]


def test_query_single_activity_still_works(monkeypatch):
    records = {"A": _record("A", "甲")}
    monkeypatch.setattr(
        router,
        "get_activities_by_ids",
        lambda act_nos: {a: records[a] for a in act_nos if a in records},
    )
    body = {"pms": {"edw_act_no": "A"}}
    resp = router._query_outbound_data("EDW_RTL_MED_ACTIVITY_BASE_INFO", body)
    assert [row["act_no"] for row in resp["result"]] == ["A"]


def test_real_excel_supports_multi_activity():
    records = data_service.get_activities_by_ids(
        ["ACT20260116906568", "ACT20260116906569", "ACT20260116906570", "NOT_EXIST"]
    )
    assert set(records) == {"ACT20260116906568", "ACT20260116906569", "ACT20260116906570"}
    body = {"pms": {"edw_act_no": "ACT20260116906568','ACT20260116906569"}}
    resp = router._query_outbound_data("EDW_RTL_MED_ACTIVITY_BASE_INFO", body)
    assert {row["act_no"] for row in resp["result"]} == {
        "ACT20260116906568",
        "ACT20260116906569",
    }
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis
python -m pytest mock/tests/test_outbound_api2_router.py -v
```
Expected: FAIL（`_split_act_nos` / `_extract_act_nos` / `get_activities_by_ids` 不存在）。

- [ ] **Step 3: 实现 `get_activities_by_ids`**

在 `mock/waihu_data_service.py` 的 `get_activity_by_id` 之后新增（保留原函数，legacy `waihu_router` 在用）:

```python
def get_activities_by_ids(act_nos: list[str]) -> dict[str, Any]:
    """根据活动编号列表批量查询，返回 {act_no: record}，未命中的编号不出现。"""
    wanted = {str(a).strip() for a in act_nos if str(a).strip()}
    if not wanted:
        return {}
    return {
        record.get("act_no"): record
        for record in load_data()
        if record.get("act_no") in wanted
    }
```

- [ ] **Step 4: 改造 `mock/outbound_api2_router.py`**

1) 导入（11-14 行）改为：

```python
try:
    from .waihu_data_service import get_activities_by_ids
except ImportError:
    from waihu_data_service import get_activities_by_ids
```

2) `_query_outbound_data` 整体替换为：

```python
def _query_outbound_data(trade_code: str, body: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    normalized_trade_code = trade_code.upper().strip()
    api_key = TRADE_CODE_ALIASES.get(normalized_trade_code)
    act_nos = _extract_act_nos(body)
    records = get_activities_by_ids(act_nos) if act_nos else {}
    rows: list[dict[str, Any]] = []
    if api_key:
        for act_no in act_nos:
            record = records.get(act_no)
            if record:
                rows.extend(_build_rows_for_record(api_key, record))
        rows = _filter_rows(rows, body)
    logger.info(
        "api2_outbound_query trade_code=%s act_nos=%s matched=%d rows=%d cost_ms=%.2f",
        normalized_trade_code,
        act_nos,
        len(records),
        len(rows),
        (time.perf_counter() - started) * 1000,
    )
    if not api_key:
        return _response([], ret_code="404", ret_msg=f"Unsupported trade_code: {trade_code}")
    return _response(rows)
```

3) `_extract_act_no` 替换为两个函数：

```python
def _extract_act_nos(body: dict[str, Any]) -> list[str]:
    pms = body.get("pms") if isinstance(body.get("pms"), dict) else {}
    params = body.get("params") if isinstance(body.get("params"), dict) else {}
    activity = body.get("activity") if isinstance(body.get("activity"), dict) else {}
    value = (
        pms.get("edw_act_no")
        or params.get("edw_act_no")
        or body.get("edw_act_no")
        or body.get("act_no")
        or body.get("actNo")
        or body.get("activity_id")
        or activity.get("act_no")
        or activity.get("actNo")
        or activity.get("activity_id")
        or activity.get("活动编号")
        or ""
    )
    return _split_act_nos(value)


def _split_act_nos(value: Any) -> list[str]:
    """解析 edw_act_no：兼容单值 A、多值 A','B','C、带首尾引号 'A','B','C' 及 list。"""
    if isinstance(value, (list, tuple)):
        items = [str(item) for item in value]
    else:
        items = str(value).split("','")
    act_nos: list[str] = []
    for item in items:
        text = item.strip().strip("'").strip()
        if text and text not in act_nos:
            act_nos.append(text)
    return act_nos
```

4) `_build_rows(api_key, record, body)` 改名为 `_build_rows_for_record(api_key, record)`：去掉 `body` 参数，函数内 5 处分支**不再调用 `_filter_rows`**，直接返回行列表：

```python
def _build_rows_for_record(api_key: str | None, record: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not api_key or not record:
        return []
    if api_key == "asset_conversion":
        rows = [
            record.get("all_customers_fund_conversion"),
            record.get("success_customers_fund_conversion"),
            record.get("failed_customers_fund_conversion"),
            record.get("effective_call_fund_conversion"),
        ]
        return [_translate(row, ASSET_CONVERSION_FIELDS) for row in rows]
    if api_key == "product_transaction":
        rows = [
            record.get("all_customers_prodtxn"),
            record.get("failed_customers_prodtxn"),
            record.get("success_customers_prodtxn"),
            record.get("effective_call_customers_prodtxn"),
        ]
        return [_translate(row, PRODUCT_TRANSACTION_FIELDS) for row in rows]
    if api_key == "activity_base_info":
        return [_translate(record.get("basic_info"), ACTIVITY_BASE_FIELDS)]
    if api_key == "outbound_call_execution":
        return [_translate(record.get("execution"), OUTBOUND_EXECUTION_FIELDS)]
    if api_key == "source_of_product_validcall":
        deposit = _translate(record.get("effective_call_deposit_source"), SOURCE_OF_PRODUCT_FIELDS)
        wealth = _translate(record.get("effective_call_wealth_source"), SOURCE_OF_PRODUCT_FIELDS)
        if deposit:
            deposit["product_type"] = "存款"
        if wealth:
            wealth["product_type"] = "理财"
        return [deposit, wealth]
    return []
```

（过滤/分页由 `_query_outbound_data` 在合行后统一调 `_filter_rows` 完成。）

- [ ] **Step 5: 运行测试确认通过**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis
python -m pytest mock/tests/test_outbound_api2_router.py -v
```
Expected: 10 passed。

- [ ] **Step 6: Commit**

```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis
git add mock/tests/test_outbound_api2_router.py mock/outbound_api2_router.py mock/waihu_data_service.py
git commit -m "mock：外呼活动查询支持 edw_act_no 多值解析与多活动合并返回

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: client 多值拼接与 matched_act_nos 聚合

**Files:**
- Modify: `backend/src/infrastructure/integrations/bank_marketing/client.py:80-139,234-250,293-304`
- Test: `backend/tests/infrastructure/__init__.py`（新建空文件）、`backend/tests/infrastructure/test_outbound_client.py`（新建）

**Interfaces:**
- Consumes: 无（独立任务）。
- Produces:
  - `BankMarketingApiClient._extract_outbound_act_nos(params: dict) -> list[str]`：str/list 归一化，去重保序去空白。
  - `_extract_outbound_act_no(params) -> str`：改为取 `_extract_outbound_act_nos` 第一个（legacy 路径兼容）。
  - `_get_outbound_activity_data_from_trade_apis` 聚合 data 新增 `matched_act_nos: list[str]`（Task 4 的 agent 命中判定依赖此字段）；`act_no`/`activity_id` 字段单活动为 str、多活动为 list[str]。
  - `pms.edw_act_no` = `"','".join(act_nos)`。

- [ ] **Step 1: 写失败测试**

Create `backend/tests/infrastructure/__init__.py`（空文件）和 `backend/tests/infrastructure/test_outbound_client.py`:

```python
"""外呼活动查询 client 多活动支持测试（mock _request_api，无网络）。"""
from __future__ import annotations

from src.infrastructure.integrations.bank_marketing.client import BankMarketingApiClient
from src.infrastructure.integrations.bank_marketing.schemas import ApiResult

TRADE = "EDW_RTL_MED_ACTIVITY_BASE_INFO"


def _client_with_fake_api(monkeypatch, rows_by_trade=None):
    client = BankMarketingApiClient()
    captured = []

    def fake_request(api_name, url, method, params):
        captured.append({"url": url, "params": params})
        trade_code = url.rsplit("/", 1)[-1]
        rows = (rows_by_trade or {}).get(trade_code, [])
        return ApiResult(
            success=True,
            data={"retCode": "000000", "totalCount": len(rows), "result": rows},
        )

    monkeypatch.setattr(client, "_request_api", fake_request)
    return client, captured


def test_extract_act_nos_from_string():
    client = BankMarketingApiClient()
    assert client._extract_outbound_act_nos({"act_no": " A "}) == ["A"]


def test_extract_act_nos_from_list_dedup_preserves_order():
    client = BankMarketingApiClient()
    assert client._extract_outbound_act_nos({"act_no": ["A", " B ", "A", ""]}) == ["A", "B"]


def test_extract_act_no_legacy_returns_first():
    client = BankMarketingApiClient()
    assert client._extract_outbound_act_no({"act_no": ["A", "B"]}) == "A"
    assert client._extract_outbound_act_no({"act_no": "A"}) == "A"


def test_edw_act_no_joined_for_multiple_activities(monkeypatch):
    client, captured = _client_with_fake_api(monkeypatch)
    client.get_outbound_activity_data({"act_no": ["A", "B", "C"]})
    assert captured, "未发起任何 trade_code 请求"
    for call in captured:
        assert call["params"]["pms"]["edw_act_no"] == "A','B','C"


def test_edw_act_no_single_activity_stays_bare(monkeypatch):
    client, captured = _client_with_fake_api(monkeypatch)
    client.get_outbound_activity_data({"act_no": "A"})
    assert captured[0]["params"]["pms"]["edw_act_no"] == "A"


def test_matched_act_nos_aggregated_from_rows(monkeypatch):
    rows = [{"act_no": "B", "act_name": "乙"}, {"act_no": "A", "act_name": "甲"}]
    client, _ = _client_with_fake_api(monkeypatch, rows_by_trade={TRADE: rows})
    result = client.get_outbound_activity_data({"act_no": ["A", "B", "C"]})
    assert result.success
    assert result.data["matched"] is True
    assert result.data["matched_act_nos"] == ["B", "A"]
    assert result.data["act_no"] == ["A", "B", "C"]
    assert result.data["activity_id"] == ["A", "B", "C"]


def test_single_activity_data_keeps_string_act_no(monkeypatch):
    rows = [{"act_no": "A", "act_name": "甲"}]
    client, _ = _client_with_fake_api(monkeypatch, rows_by_trade={TRADE: rows})
    result = client.get_outbound_activity_data({"act_no": "A"})
    assert result.data["act_no"] == "A"
    assert result.data["matched_act_nos"] == ["A"]


def test_empty_act_no_returns_error():
    client = BankMarketingApiClient()
    result = client.get_outbound_activity_data({"act_no": ["", "  "]})
    assert not result.success
    assert "缺少act_no" in result.error
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis/backend
python -m pytest tests/infrastructure/test_outbound_client.py -v
```
Expected: FAIL（`_extract_outbound_act_nos` 不存在 / `matched_act_nos` 断言失败）。

- [ ] **Step 3: 实现 `_extract_outbound_act_nos` 并改造 `_extract_outbound_act_no`**

替换 `client.py:293-304` 的 `_extract_outbound_act_no` 为：

```python
    def _extract_outbound_act_nos(self, params: dict) -> list[str]:
        """提取活动编号列表：act_no/activity_id 兼容 str 或 list，去重保序去空白。"""
        activity = params.get("activity") if isinstance(params.get("activity"), dict) else {}
        value = (
            params.get("act_no")
            or params.get("activity_id")
            or activity.get("act_no")
            or activity.get("activity_id")
            or activity.get("actNo")
            or activity.get("活动编号")
            or ""
        )
        items = value if isinstance(value, (list, tuple)) else [value]
        act_nos: list[str] = []
        for item in items:
            text = str(item).strip()
            if text and text not in act_nos:
                act_nos.append(text)
        return act_nos

    def _extract_outbound_act_no(self, params: dict) -> str:
        act_nos = self._extract_outbound_act_nos(params)
        return act_nos[0] if act_nos else ""
```

- [ ] **Step 4: 改造 `_get_outbound_activity_data_from_trade_apis` 与 `_build_outbound_trade_api_params`**

`_get_outbound_activity_data_from_trade_apis`（client.py:80-139）整体替换为：

```python
    def _get_outbound_activity_data_from_trade_apis(self, params: dict) -> ApiResult:
        act_nos = self._extract_outbound_act_nos(params)
        if not act_nos:
            return ApiResult(success=False, error="外呼活动查询缺少act_no/activity_id")

        edw_act_no = "','".join(act_nos)
        sources: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        any_success = False
        matched = False
        matched_act_nos: list[str] = []
        trade_codes = self._outbound_activity_trade_codes()
        if not trade_codes:
            return ApiResult(success=False, error="外呼活动交易码未配置")

        for trade_code in trade_codes:
            url = self._build_outbound_trade_api_url(trade_code)
            request_params = self._build_outbound_trade_api_params(params, edw_act_no)
            result = self._request_api(
                api_name=f"外呼活动查询API[{trade_code}]",
                url=url,
                method=self._settings.bank_marketing_outbound_activity_data_method,
                params=request_params,
            )
            if not result.success:
                errors[trade_code] = result.error
                sources[trade_code] = {"totalCount": 0, "result": [], "error": result.error}
                continue

            any_success = True
            rows = self._normalize_outbound_trade_rows(result.data)
            total_count = len(rows)
            if total_count > 0:
                matched = True
            for row in rows:
                row_act_no = str(row.get("act_no") or "").strip()
                if row_act_no and row_act_no not in matched_act_nos:
                    matched_act_nos.append(row_act_no)
            sources[trade_code] = {
                "totalCount": total_count,
                "result": rows,
            }

        if not any_success:
            return ApiResult(success=False, error="; ".join(errors.values()) or "外呼活动查询API全部失败")

        total_count = sum(source.get("totalCount", 0) for source in sources.values())
        act_no_value: str | list[str] = act_nos[0] if len(act_nos) == 1 else act_nos
        data = {
            "matched": matched,
            "activity_id": act_no_value,
            "act_no": act_no_value,
            "matched_act_nos": matched_act_nos,
            "source": "outbound_activity_trade_apis",
            "totalCount": total_count,
            "sources": sources,
        }
        if errors:
            data["errors"] = errors
        return ApiResult(
            success=True,
            data=data,
            meta={
                "count": total_count,
                "matched": matched,
                "trade_codes": trade_codes,
            },
        )
```

`_build_outbound_trade_api_params`（client.py:234-250）第二参数改名 `edw_act_no`（调用方已传入拼接好的值）：

```python
    def _build_outbound_trade_api_params(self, params: dict, edw_act_no: str) -> dict:
        raw_props = params.get("props") if isinstance(params.get("props"), dict) else {}
        raw_pms = params.get("pms") if isinstance(params.get("pms"), dict) else {}
        pms = {
            "edw_act_no": edw_act_no,
            "edw_customer_segment": raw_pms.get("edw_customer_segment") or "",
            "edw_product_type": raw_pms.get("edw_product_type") or "",
        }
        return {
            "pms": pms,
            "props": {
                "limit": raw_props.get("limit") or params.get("limit") or 200,
                "start": raw_props.get("start") or params.get("start") or 1,
                "identity": self._build_identity(params),
                "seqNo": self._build_seq_no(params),
            },
        }
```

- [ ] **Step 5: 运行测试确认通过**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis/backend
python -m pytest tests/infrastructure/test_outbound_client.py -v
```
Expected: 8 passed。

- [ ] **Step 6: 确认无存量回归**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis/backend
python -m pytest tests -q
```
Expected: 全量通过（`tests/agent_v2/test_outbound_perspective.py` 在 Task 4 才改，若此处有个别失败且失败原因确为"合并调用尚未实现"，记录后在 Task 4 修复；其余失败必须解决）。

- [ ] **Step 7: Commit**

```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis
git add backend/src/infrastructure/integrations/bank_marketing/client.py backend/tests/infrastructure/
git commit -m "client：外呼活动查询支持多活动 edw_act_no 拼接与 matched_act_nos 聚合

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: agent 合并探测 + 逐活动拆分 + 失败回退

**Files:**
- Modify: `backend/src/agent_v2/tools/report_gen.py:143-176`（重构 `_probe_outbound_activities`，新增 `_probe_outbound_merged`、`_split_outbound_data`、`_probe_outbound_activities_individually`）
- Test: `backend/tests/agent_v2/test_outbound_perspective.py`（改造 + 新增回退用例）

**Interfaces:**
- Consumes: Task 3 的聚合 data 结构（`matched_act_nos: list[str]`、`sources[trade_code]["result"]` 行内含 `act_no` 字段）。
- Produces:
  - `_probe_outbound_activities(activities, ctx) -> dict[str, dict]`：签名与返回结构不变（`{key: {"status", "data", "error"}}`），内部改为合并探测 + 回退。
  - `_split_outbound_data(data: dict, act_key: str) -> dict`：从聚合 data 拆出单活动数据（过滤 sources 行、重算 totalCount、`act_no`/`activity_id` 置为该活动）。
  - 下游 `outbound_map` 结构不变（`{act_key: data}`）。

- [ ] **Step 1: 改造测试文件（先写失败测试）**

在 `backend/tests/agent_v2/test_outbound_perspective.py` 中：

1) `_patch_probe` 整体替换为（同时新增 `_merged_data` 辅助函数）：

```python
def _merged_data(found: set[str]) -> dict:
    rows = [{"act_no": key, "act_name": f"活动{key}"} for key in sorted(found)]
    return {
        "matched": bool(found),
        "matched_act_nos": sorted(found),
        "act_no": sorted(found),
        "activity_id": sorted(found),
        "totalCount": len(rows),
        "sources": {
            "EDW_RTL_MED_ACTIVITY_BASE_INFO": {"totalCount": len(rows), "result": rows},
        },
    }


def _patch_probe(monkeypatch, found_keys=(), error_keys=(), merged_error=False):
    """mock 外呼接口：act_no 为 list 走合并探测，为 str 走回退逐活动探测。"""
    calls = []

    def fake_fetch(params):
        calls.append(params)
        key = params["act_no"]
        if isinstance(key, list):
            if merged_error:
                return SimpleNamespace(success=False, data=None, error="连接超时")
            found = set(key) & set(found_keys)
            return SimpleNamespace(success=True, data=_merged_data(found), error="")
        if key in error_keys:
            return SimpleNamespace(success=False, data=None, error="连接超时")
        if key in found_keys:
            return SimpleNamespace(success=True, data={"接通率": 0.6}, error="")
        return SimpleNamespace(success=True, data={"matched": False}, error="")

    monkeypatch.setattr(rg, "fetch_outbound_activity_data", fake_fetch)
    return calls
```

2) `test_probe_params_carry_no_dates` 断言改为：

```python
def test_probe_params_carry_no_dates(monkeypatch):
    calls = _patch_probe(monkeypatch, found_keys={"act-1", "act-2", "act-3"})
    _patch_pipeline_capture(monkeypatch)
    _call(perspective="outbound_call_analysis", confirm_mixed=True)
    assert len(calls) == 1, "多活动应合并为一次外呼探测调用"
    params = calls[0]
    assert params["act_no"] == ["act-1", "act-2", "act-3"]
    assert "start_date" not in params and "end_date" not in params
    assert "actStartDt" not in params and "actEndDt" not in params
```

3) `test_mixed_confirmed_enters_pipeline_with_map` 中 map 断言改为：

```python
    assert set(seed["outbound_activity_data_map"]) == {"act-1"}
    data = seed["outbound_activity_data_map"]["act-1"]
    assert data["act_no"] == "act-1"
    for source in data["sources"].values():
        assert all(row["act_no"] == "act-1" for row in source["result"])
```

4) `test_all_outbound_multi_activity_no_confirm_needed` 末尾追加拆分断言：

```python
    data_map = seeds[0]["outbound_activity_data_map"]
    assert len(data_map) == 3
    for key, data in data_map.items():
        assert data["act_no"] == key
        for source in data["sources"].values():
            assert all(row["act_no"] == key for row in source["result"])
```
（原 `assert len(seeds[0]["outbound_activity_data_map"]) == 3` 被上面的 `len(data_map) == 3` 覆盖，可删。）

5) `test_single_outbound_hit_direct_mode` 中：

```python
    assert seeds[0]["outbound_activity_data"]["act_no"] == "act-1"
```
（替换原 `== {"接通率": 0.6}` 断言。）

6) 末尾端到端用例的 `assert len(calls) == 6, "两次调用各探测 3 个活动"` 改为：

```python
    assert len(calls) == 2, "两次 generate_report 各一次合并探测"
```

7) `test_all_probe_calls_fail_reports_api_error`：合并调用不走 `error_keys`，必须让合并调用也失败才会回退并全部 error，首行改为：

```python
def test_all_probe_calls_fail_reports_api_error(monkeypatch):
    _patch_probe(monkeypatch, error_keys={"act-1", "act-2", "act-3"}, merged_error=True)
```

8) `test_partial_probe_failure_marks_activity_in_confirm`：同理，逐活动 error 只在回退路径发生，整体替换为：

```python
def test_partial_probe_failure_marks_activity_in_confirm(monkeypatch):
    """合并探测失败回退逐活动探测后，单个活动失败在确认提示中标注。"""
    calls = _patch_probe(monkeypatch, found_keys={"act-1"}, error_keys={"act-2"}, merged_error=True)
    content = _call(perspective="outbound_call_analysis")
    payload = json.loads(content)
    assert payload["status"] == "need_confirm"
    assert payload["non_outbound_query_failed"] == ["短信营销"]
    assert set(payload["non_outbound_activities"]) == {"短信营销", "厅堂活动"}
    merged_calls = [c for c in calls if isinstance(c["act_no"], list)]
    individual_calls = [c for c in calls if isinstance(c["act_no"], str)]
    assert len(merged_calls) == 1, "先尝试一次合并探测"
    assert len(individual_calls) == 3, "回退后逐活动探测 3 个活动"
```

9) 文件末尾新增回退异常路径用例：

```python
def test_merged_probe_exception_falls_back_to_individual(monkeypatch):
    def fake_fetch(params):
        if isinstance(params["act_no"], list):
            raise ConnectionError("网络不可达")
        return SimpleNamespace(success=True, data={"matched": False}, error="")

    monkeypatch.setattr(rg, "fetch_outbound_activity_data", fake_fetch)
    _patch_pipeline_capture(monkeypatch)
    content = _call(perspective="outbound_call_analysis")
    assert "所选的活动均不是外呼活动" in content
```

- [ ] **Step 2: 运行测试确认失败**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis/backend
python -m pytest tests/agent_v2/test_outbound_perspective.py -v
```
Expected: 多数 FAIL（合并调用/拆分/回退未实现；逐活动逻辑会把 list 当 key 导致行为不符）。

- [ ] **Step 3: 重构 `report_gen.py:143-176`**

将 `_probe_outbound_activities`（含内部 `probe` 函数）整体替换为以下四个函数：

```python
async def _probe_outbound_activities(activities: list[dict], ctx) -> dict[str, dict]:
    """合并调外呼数据接口探测外呼活动；失败回退逐活动探测。

    入参仅活动编号（act_no）+ 用户上下文，不传开始/结束时间（设计文档 §5.1）。
    返回 {activity_key: {"status": "found"|"not_found"|"error", "data": dict, "error": str}}。
    """
    keys: list[str] = []
    for activity in activities:
        key = activity_key(activity)
        if key and key not in keys:
            keys.append(key)
    if not keys:
        return {}
    merged = await _probe_outbound_merged(keys, ctx)
    if merged is not None:
        return merged
    return await _probe_outbound_activities_individually(activities, ctx)


async def _probe_outbound_merged(keys: list[str], ctx) -> dict[str, dict] | None:
    """一次合并调用探测全部活动；成功返回探测结果，失败返回 None（触发回退）。"""
    try:
        result = await asyncio.to_thread(
            fetch_outbound_activity_data,
            {
                "act_no": keys,
                "activity_id": keys,
                "user_id": getattr(ctx, "user_id", "") or "",
                "org_no": getattr(ctx, "org_no", "") or "",
                "channel": getattr(ctx, "channel", "") or "",
            },
        )
    except Exception as exc:  # 网络/超时等按调用失败处理，回退逐活动探测
        logger.warning("外呼合并探测异常，回退逐活动探测: %s", exc)
        return None
    if not result.success:
        logger.warning("外呼合并探测失败，回退逐活动探测: %s", result.error)
        return None
    data = result.data or {}
    matched = data.get("matched_act_nos") if isinstance(data, dict) else None
    if not isinstance(matched, list):  # 旧式响应无法逐活动判定，回退逐活动探测
        logger.warning("外呼合并探测响应缺少 matched_act_nos，回退逐活动探测")
        return None
    matched_set = {str(item) for item in matched}
    return {
        key: {
            "status": "found" if key in matched_set else "not_found",
            "data": _split_outbound_data(data, key) if key in matched_set else {},
            "error": "",
        }
        for key in keys
    }


def _split_outbound_data(data: dict, act_key: str) -> dict:
    """从合并调用的聚合 data 中拆分出单个活动的数据（过滤 sources 行、重算 totalCount）。"""
    sources = data.get("sources")
    if not isinstance(sources, dict):
        return dict(data)
    split_sources: dict[str, dict] = {}
    total = 0
    for trade_code, source in sources.items():
        if not isinstance(source, dict):
            split_sources[trade_code] = source
            continue
        rows = [
            row
            for row in (source.get("result") or [])
            if isinstance(row, dict) and str(row.get("act_no") or "") == act_key
        ]
        split_sources[trade_code] = {**source, "totalCount": len(rows), "result": rows}
        total += len(rows)
    return {
        **data,
        "act_no": act_key,
        "activity_id": act_key,
        "totalCount": total,
        "sources": split_sources,
    }


async def _probe_outbound_activities_individually(activities: list[dict], ctx) -> dict[str, dict]:
    """逐个调外呼数据接口探测活动是否为外呼活动（合并探测失败时的回退路径）。"""

    async def probe(activity: dict) -> tuple[str, dict]:
        key = activity_key(activity)
        try:
            result = await asyncio.to_thread(
                fetch_outbound_activity_data,
                {
                    "act_no": key,
                    "activity_id": key,
                    "user_id": getattr(ctx, "user_id", "") or "",
                    "org_no": getattr(ctx, "org_no", "") or "",
                    "channel": getattr(ctx, "channel", "") or "",
                },
            )
        except Exception as exc:  # 网络/超时等按调用失败处理
            return key, {"status": "error", "data": {}, "error": str(exc)}
        if not result.success:
            return key, {"status": "error", "data": {}, "error": result.error or "调用失败"}
        data = result.data or {}
        found = bool(data and not (isinstance(data, dict) and data.get("matched") is False))
        return key, {
            "status": "found" if found else "not_found",
            "data": data if found else {},
            "error": "",
        }

    pairs = await asyncio.gather(*(probe(activity) for activity in activities))
    return dict(pairs)
```

- [ ] **Step 4: 运行测试确认通过**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis/backend
python -m pytest tests/agent_v2/test_outbound_perspective.py -v
```
Expected: 全部 passed（含新增异常回退用例与两个改造后的 error 用例）。

- [ ] **Step 5: 运行 agent 相关测试确认无回归**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis/backend
python -m pytest tests/agent_v2 -q
```
Expected: 全部通过。

- [ ] **Step 6: Commit**

```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis
git add backend/src/agent_v2/tools/report_gen.py backend/tests/agent_v2/test_outbound_perspective.py
git commit -m "agent：外呼视角探测改为多活动合并调用，失败回退逐活动探测

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 全量回归 + mock 真实服务冒烟

**Files:**
- 无代码改动（验证任务；如发现问题回到对应任务修复）。

**Interfaces:**
- Consumes: Task 1-4 全部产物。

- [ ] **Step 1: backend 全量测试 + lint**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis/backend
python -m pytest tests -q
ruff check src/infrastructure/integrations/bank_marketing/client.py src/agent_v2/tools/report_gen.py tests/infrastructure/test_outbound_client.py tests/agent_v2/test_outbound_perspective.py
```
Expected: 测试全通过；ruff 无告警（ruff 未安装则跳过并注明）。

- [ ] **Step 2: mock 测试**

Run:
```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis
python -m pytest mock/tests -q
```
Expected: 10 passed。

- [ ] **Step 3: mock 真实服务冒烟（多活动端到端）**

启动 mock 服务并用 curl 验证多值查询：

```bash
cd /Users/lihongjun/Desktop/NJ_BANK/Marketing_Campaign_Analysis/njbank_Marketing_Campaign_Analysis
python -m uvicorn mock.app:app --port 8005 &
sleep 3
curl -s -X POST "http://localhost:8005/api2/dataservice/query/EDW_RTL_MED_ACTIVITY_BASE_INFO" \
  -H "Content-Type: application/json" \
  -d '{"pms": {"edw_act_no": "ACT20260116906568'"'"','"'"'ACT20260116906569"}, "props": {"limit": 20, "start": 1}}'
kill %1
```
Expected: 返回 `retCode=000000`，`result` 含 2 行，`act_no` 分别为 `ACT20260116906568` 和 `ACT20260116906569`。

（若 8005 端口被占用，先确认占用进程是否为本项目 mock：是则直接用它发 curl，不做 kill；不是则换端口重试。）

- [ ] **Step 4: 汇总验证结果**

向用户报告：各测试套件通过数、冒烟结果、涉及的 commit 列表（`git log --oneline -5`）。

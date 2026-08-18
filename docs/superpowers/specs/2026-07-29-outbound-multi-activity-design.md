# 外呼活动多活动查询支持 — 设计文档

日期：2026-07-29
状态：已确认（方案 A）

## 1. 背景与目标

外呼活动查询 API（数据服务 `/dataservice/query/{trade_code}`）的入参 `edw_act_no` 支持传入多个活动编号：值形如 `A','B','C`（值内已含中间引号，**首尾引号由服务端补全**，最终拼进 SQL `IN ('A','B','C')`）。

当前系统现状：

- agent 工具 `generate_report(activity_ids=[...])` 入参本就是列表，但 `_probe_outbound_activities`（`backend/src/agent_v2/tools/report_gen.py:143`）是**逐活动循环单值调用**（N 个活动 → N 次请求），从未合并为一次多值调用。
- client（`backend/src/infrastructure/integrations/bank_marketing/client.py`）`_extract_outbound_act_no` 只取单值，`edw_act_no` 原样透传。
- mock（`mock/outbound_api2_router.py`）`_extract_act_no` 无拆分逻辑，多值字符串会整体匹配失败；Excel 数据源（`mock/外呼活动 mock 数据.xlsx`）目前只有 1 条活动 `ACT20260116906568`。

目标：

1. 智能体支持多活动合并查询外呼活动数据（一次调用，N 个活动 → 1 次请求）。
2. mock 支持解析多值 `edw_act_no`。
3. mock 数据源补充活动数据，支撑多活动场景测试。

## 2. 方案（已选定：方案 A）

**合并调用为主 + 失败回退逐活动探测；多值拼接逻辑收敛在 client 一处。**

否决的备选：

- 方案 B（合并调用无回退）：合并调用一次失败则全部活动 error，健壮性低于现状（现状单活动失败不影响其他活动）。
- 方案 C（agent 拼字符串、client 纯透传）：多值格式契约泄漏到 agent 层，client 无法校验/复用。

## 3. 数据流（改动后）

```
generate_report(activity_ids=[A,B,C])
  → _resolve_activities() → 活动快照列表（不变）
  → _probe_outbound_activities()  一次合并调用
      → fetch_outbound_activity_data({"act_no": [A,B,C], "activity_id": [A,B,C], ...})
          → client._extract_outbound_act_nos() → [A,B,C]（去重、保序、去空白）
          → "','".join(act_nos) → "A','B','C" 放入 pms.edw_act_no
          → 逐 trade_code 调用（不变）
          → 聚合时新增 matched_act_nos（从各 trade_code 返回行的 act_no 字段收集去重）
      合并调用抛异常或 success=False → 回退现有逐活动单值探测
  → 命中判定：act_no ∈ matched_act_nos → found，否则 not_found
  → 命中活动的 data：从 sources 中过滤出该 act_no 的行，逐活动拆分
```

## 4. client 改动（`backend/src/infrastructure/integrations/bank_marketing/client.py`）

1. **新增 `_extract_outbound_act_nos(params) -> list[str]`**：`act_no` / `activity_id` 的值兼容 `str` 或 `list[str]`，统一归一化为去重、保序、去空白的列表；全部为空返回 `[]`。
2. **保留 `_extract_outbound_act_no`**：legacy 路径 `_build_outbound_activity_data_url` 的 `{act_no}` 占位仍用单值（列表取第一个），行为不变。
3. **`_get_outbound_activity_data_from_trade_apis`**：
   - 改用 `_extract_outbound_act_nos`；空列表 → 返回现有错误 `"外呼活动查询缺少act_no/activity_id"`。
   - `edw_act_no` 值为 `"','".join(act_nos)`（单活动时就是裸值 `A`，服务端补引号后语义与现状一致）。
   - 聚合 data 新增 `matched_act_nos: list[str]`：遍历各 trade_code 返回行的 `act_no` 字段去重收集；`matched` 保持原全局语义（任意行即 True）。
   - data 的 `act_no` / `activity_id` 字段：多活动时为列表，单活动保持字符串（兼容现有消费方）。

## 5. agent 改动（`backend/src/agent_v2/tools/report_gen.py`）

1. **`_probe_outbound_activities` 重构为两段**：
   - **合并探测**：所有活动 key 去重后一次调用 `fetch_outbound_activity_data`；`success=True` 时按 `matched_act_nos` 逐活动判定 found / not_found。
   - **回退**：合并调用抛异常或 `success=False` → 走现有逐活动探测逻辑（原样保留，改名 `_probe_outbound_activities_individually`）。
2. **命中活动的 data 逐活动拆分**：合并调用返回的 data 是全部活动的聚合，拆分时从 `sources[trade_code]["result"]` 过滤出 `row["act_no"] == act_key` 的行、重算 `totalCount`，保持下游消费结构不变。
   - 下游消费点已核实：`outbound_map` 的值作为 `outbound:<act_no>` 命名空间的 `values` 进报告组件数据（`report_gen.py:402-420`），因此每个活动的数据必须只含自己的行。
3. **工具 schema / prompt 不改**：`activity_ids` 本来就是 `list[str]`。
4. 报告管线备用节点 `outbound_activity_data_fetch_node`（仅单活动场景）不改。

## 6. mock 改动（`mock/outbound_api2_router.py`、`mock/waihu_data_service.py`）

1. **`_extract_act_no` → `_extract_act_nos(body) -> list[str]`**：取到原始字符串后按 `','` 拆分，逐项 `strip()` 并剥掉首尾单引号。三种形态均正确解析：
   - `A` → `[A]`
   - `A','B','C` → `[A, B, C]`
   - `'A','B','C'`（带首尾引号）→ `[A, B, C]`
2. **新增 `get_activities_by_ids(act_nos) -> dict[str, dict]`**（`waihu_data_service.py`）：返回 `{act_no: record}`；查不到的 act_no 不出现——**模拟真实 IN 查询语义：无数据的活动不产出行**，这是 agent 判定 not_found 的依据。原 `get_activity_by_id` 保留（legacy 路由使用）。
3. **`_query_outbound_data`**：对所有命中的 record 分别 `_build_rows` 后合并，再走现有 `_filter_rows`（客群/产品类型过滤 + 分页）。行内本就带 `act_no` 字段，调用方可区分归属。
4. GET 路由与 legacy `waihu_router` 单值路径走同一解析函数，单值行为不变。

## 7. mock 数据补充

用 openpyxl 一次性脚本（不留仓库）往 `mock/外呼活动 mock 数据.xlsx` 追加 2 条活动：复制 `ACT20260116906568` 的 13 个数据块，改 `act_no` 为 `ACT20260116906569` / `ACT20260116906570`，数值微调以便区分。

## 8. 错误处理

| 场景 | 行为 |
|---|---|
| 合并调用抛异常或 `success=False` | 回退逐活动探测（现有逻辑原样保留），逐活动 error 语义不变 |
| 合并调用成功但某活动无行 | 该活动 not_found，走现有"非外呼活动"确认流程，不变 |
| 全部活动 error | 返回"外呼活动数据查询失败：…"（现有行为） |
| 活动编号全部为空 | 返回"外呼活动查询缺少act_no/activity_id"（现有行为） |

## 9. 测试

| 层 | 测试文件 | 内容 |
|---|---|---|
| mock | 新建 `mock/tests/test_outbound_api2_router.py`（mock 首个测试，需配 pytest 可运行） | 多值三种形态解析、多活动合并返回、部分活动不存在、单值兼容 |
| client | 新建 `backend/tests/infrastructure/test_outbound_client.py` | list/str 入参归一化、`edw_act_no` 拼接格式、`matched_act_nos` 聚合 |
| agent | 改造 `backend/tests/agent_v2/test_outbound_perspective.py` | "每活动一次调用"断言 → "一次合并调用 + 按 matched_act_nos 判定"；新增回退路径用例（合并调用失败 → 逐活动探测） |

## 10. 非目标（YAGNI）

- 不改 legacy 外呼查询路径（`{act_no}` URL 占位模式）的多值支持。
- 不改 `generate_report` 工具 schema 与 prompt 文案。
- 不改报告管线其他节点；`outbound_activity_data_fetch_node` 保持单活动逻辑。
- 不给 mock 的 legacy `waihu_router`（`/waihu/activities/{act_no}`）加多值支持。

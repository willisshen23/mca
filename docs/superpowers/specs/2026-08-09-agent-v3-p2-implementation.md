# agent_v3 P2 实施记录：持久化与会话重载

> 日期：2026-08-09
> 依据：`2026-08-09-agent-v3-p2-persistence-design.md`（已批准决策：SQLite 先行 / 混合重载 / 不含审批跨重启恢复）
> 状态：**已完成实机联调验收（2026-08-10，6 项全过）**，验收记录 `2026-08-10-agent-v3-p2-acceptance.md`

## 实施清单

| 设计项 | 落地 | 位置 |
|---|---|---|
| 4.1 持久化接线 | `init/close_v3_checkpointer`，conf=sqlite+WAL+timeout 5s；lifespan 在 `Runner.start()` 前 init、shutdown 时 close（dispose engine + 恢复 in_memory 默认） | [agent_v3/state/persistence.py](../../../backend/src/agent_v3/state/persistence.py)、[main.py](../../../backend/src/main.py) |
| 配置项 | `agent_v3_checkpointer_db_path`（env `AGENT_V3_CHECKPOINTER_DB_PATH`，默认 `data/v3_checkpoints.db`，与 v2 `checkpoints.db` 物理隔离） | [config.py](../../../backend/src/config.py) |
| 4.2 重载重写 | `GET /conversations/{id}` 业务表驱动：messages←conversation_turn（过滤审批审计轮、failed 无回复轮）；html_report←report_versions 最新版本（`get_latest_report_html_by_thread`，复用 get_report_asset 回退链）；report_context/runtime_trace 降级 `{}`（前端 `addRuntimeTrace` 对空 plan 容错，已核实 UiChatView.vue:1408）；响应字段名/结构不变 | [conversations.py](../../../backend/src/api/routers/conversations.py) |
| 4.2 删除清理 | `DELETE /conversations/{id}` 保留原行为，追加 `delete_v3_thread_checkpoint`（kv_store 键前缀 `{thread_id}:` 直删；文件/表不存在静默跳过） | 同上 + persistence.py |
| 风险 2 final_response | done 帧 `final_response`/`html_report` 接进 `finish_turn`（v2/v3 runtime 四处调用点同步改，v2 同受益——重载 v2 老会话也靠它） | [agent_v3/runtime.py](../../../backend/src/agent_v3/runtime.py)、[agent_v2/runtime.py](../../../backend/src/agent_v2/runtime.py) |
| 风险 3 kv 表 | 已核实：`DbBasedKVStore` 表名 `kv_store`，首次读写自动 `CREATE TABLE`（`_create_table_if_not_exist`）；键结构 `{session_id}:agent:{agent_id}:agent_state_blobs[…_dump_type]` | 框架源码确认 |

## 离线测试（新增 8 例，全绿）

- `tests/agent_v3/test_v3_persistence.py`（4）：conf 正确性（monkeypatch factory）；**关键集成——真实 PersistenceCheckpointer + 临时 SQLite，保存后全新 checkpointer + 全新同 thread_id 会话恢复业务键**（模拟进程重启）；删除清理（前缀删除/他线程不受影响/文件缺失/表缺失静默）。
- `tests/test_conversations_reload.py`（4）：`_messages_from_turns` 过滤口径；`get_latest_report_html_by_thread` 版本提取；`get_conversation` 全量组装（内存 SQLite 业务库）；空 thread 降级。

全量套件：299 passed + 2 failed（`test_tools_report_export` 两例为 M3 既有问题，仅支持 HTML 导出而测试未同步，非本次回归——失败签名与变更前一致）。

## 与设计的偏差

1. `CheckpointerConfig` 不在 `openjiuwen.core.session.checkpointer` 包导出里，改从 `.checkpointer.checkpointer` 子模块导入（包 `__init__` 只导出 Factory/Provider）。
2. `finish_turn` 除 `final_response` 外同时接入 `html_report`（同一 done 帧免费获得），`conversation_turn.has_report` 不再恒为 False。
3. 设计 §4.2 称"移除 `_get_checkpoint_saver`"——实际保留：`DELETE` 仍用它清 v2 langgraph checkpoint；移除的是 GET 重载里的 checkpoint 读取及随之失效的 `_runtime_trace_from_checkpoint`/`_compact_*`/`_message_*` 系列helper。

## 待人工联调清单（设计 §6）

1. 重启服务后续聊（引用重启前上下文）；2. 刷新恢复消息列表+报告卡片（含多版本）；3. 删除会话（meta + v3 checkpoint 都清）；4. v2 老会话在 v3 下恢复；5. `AGENT_V3_ENABLED=false` 回归（v2 重载也走业务表）；6. 审批挂起中重启 → 历史可见、可继续对话（审批作废，预期行为）。

# openJiuwen 迁移 P2 设计：持久化与会话重载

> 日期：2026-08-09
> 前置：调研 `2026-08-07-openjiuwen-agent-core-migration-research.md` §4 P2；P1 验收 `2026-08-07-agent-v3-p1-acceptance.md`
> 已批准决策（2026-08-09 与用户对齐）：**① SQLite 先行（MySQL 后续换 conf 即可）；② 混合重载（展示走业务表、续聊走 checkpoint）；③ 不含审批中断的跨重启恢复**

## 1. 目标与范围

解决 P1 唯一用户可见降级：**进程重启/页面刷新后会话历史与上下文丢失**。

- **In scope**：v3 checkpointer 持久化接线（SQLite）；`GET /conversations/{id}` 重载改为业务表驱动（v2/v3 通吃）；删除会话时清理 v3 checkpoint；进程重启后同 thread_id 续聊。
- **Out of scope**：审批中断的跨重启恢复（pending_interrupt 保持进程内）；MySQL checkpointer（conf 预留，本阶段不验证）；runtime_trace / report_context 的重载恢复（降级为空）；分层模型路由；P3 报告管线迁 Workflow。

## 2. 关键事实（源码已核实）

1. **框架自带持久化 checkpointer**：`openjiuwen/core/session/checkpointer/persistence.py` 的 `PersistenceCheckpointer`，经 `@CheckpointerFactory.register("persistence")` 注册。`CheckpointerFactory.create(CheckpointerConfig(type="persistence", conf=...))` 创建 + `set_default_checkpointer(...)` 设为全局默认。conf 支持 `{"db_type":"sqlite", "db_path", "db_timeout"（默认30）, "db_enable_wal"（默认True）, "db_client"（可传预构 AsyncEngine → MySQL 通道）}`；SQLite 走 SQLAlchemy `sqlite+aiosqlite` + WAL + `DbBasedKVStore`。
2. **agent 状态序列化**：`session.state().get_state(copied=False)` 整体 pickle（`create_serializer("pickle")`），含业务键与消息上下文（context_engine 的 `save_contexts` 保存 messages/滑窗/token 统计进 session state）。恢复：`pre_agent_execute` → `AgentStorage.recover` → `set_state`。
3. **反序列化容错**：recover 内部 deserialize 失败返回 None（全新状态起步），不抛错。
4. **重载链路现状**：`conversations.py:312-374` 从 langgraph checkpoint `channel_values` 读 `messages/html_report/report_context/plan` + runtime 键；`report_histories/report_placements` 本就走 `agent_run_history`/`report_versions` 业务表；`GET /conversations` 列表走 `conversation_meta`（不依赖 checkpoint）。
5. **业务表已持久化的内容**：`conversation_turn`（request_id/thread_id/user_text/assistant_response/has_report/status/started_at/finished_at，`get_thread_turns` 可取全量）；`report_versions.report_asset_blob`（全版本报告 HTML 本体）+ `agent_run_history.latest_version_no`；v2 时期与 v3（经 v2 工具复用）都在写。
6. **删除会话现状**（`conversations.py:405-436`）：删 langgraph checkpoint 两表 + `conversation_meta`；不删 conversation_turn/agent_run_history/report_versions（保留行为不变）。
7. 前端恢复链（`UiChatView.vue` + `api/conversations.js`）消费 `GET /conversations/{id}` 的 `{messages, htmlReport, reportContext, reportHistory, reportHistories, reportPlacements, runtimeTrace}`——**响应字段名与结构必须保持不变**。
8. v2 的 `AsyncSqliteSaver` 连接 `data/checkpoints.db`；v3 checkpoint 用独立文件 `data/v3_checkpoints.db`，物理隔离。
9. `conversation_turn.user_text` 提取会过滤"已选择…继续分析"续跑话术；审批轮的 user_text 是"已审批 {tool}：{decision}"审计文本——重建消息列表时须过滤 `已审批` 前缀（与 `_report_placements` 既有口径一致）。

## 3. 架构

```
┌─ agent_v3 runtime ─┐     ┌─ CheckpointerFactory ──────────────┐
│ new_run_session     │────→│ "persistence" provider（框架自带）  │
│ （每轮新建会话实例）  │     │  SQLite: data/v3_checkpoints.db    │
└─────────────────────┘     │  pickle blob，WAL，仅框架读写       │
                            └────────────────────────────────────┘
┌─ GET /conversations/{id} ─┐  ┌─ 业务表（稳定 schema，应用层读）───┐
│ 重载重写：不读任何           │←─│ conversation_turn：消息列表        │
│ checkpoint（v2/v3 通吃）     │  │ report_versions：报告全版本 HTML   │
└───────────────────────────┘  │ conversation_meta：列表/归属        │
                               └───────────────────────────────────┘
```

核心原则：**checkpoint blob 只有框架自己读写**（续聊状态），**应用层重载只读业务表**（展示历史）。

## 4. 组件设计

### 4.1 v3 持久化接线（新建 `backend/src/agent_v3/state/persistence.py`）

- `async def init_v3_checkpointer() -> None`：`CheckpointerFactory.create(CheckpointerConfig(type="persistence", conf={...}))` → `CheckpointerFactory.set_default_checkpointer(...)`。conf：`db_type="sqlite"`、`db_path=str(resolve_path(settings.agent_v3_checkpointer_db_path))`、`db_timeout=5`、`db_enable_wal=True`。
- `async def close_v3_checkpointer() -> None`：置空默认（engine 随进程退出，无需显式 dispose；如需可持有引用调 `engine.dispose()`）。
- 配置项（config.py）：`agent_v3_checkpointer_db_path: str = "data/v3_checkpoints.db"`（env `AGENT_V3_CHECKPOINTER_DB_PATH`）。
- lifespan 接线（main.py，均包在 `agent_v3_enabled` 开关内）：startup 在 `Runner.start()` 之前调用 `init_v3_checkpointer()`；shutdown 调 `close_v3_checkpointer()`。
- `new_run_session` 不变：框架 pre_run 自动 recover、post_run 自动 save，中断时 `interrupt_agent_execute` 也会 save（但恢复审批不在范围）。

### 4.2 会话重载重写（`backend/src/api/routers/conversations.py`）

`GET /conversations/{id}` 改业务表驱动，响应字段名/结构保持不变：

| 响应字段 | 新数据源 |
|---|---|
| `messages` | `get_thread_turns(thread_id)`：过滤 status=failed 且无 assistant_response 的轮、`user_text` 以"已审批"开头的审计轮；每轮 → `{"role":"user","content":user_text}` +（有 assistant_response 时）`{"role":"ai","content":assistant_response}`，按 started_at 排序 |
| `html_report` | `report_versions` 最新报告（`agent_run_history.latest_version_no` 对应版本）的 `report_asset_blob`，经 `strip_report_footer_note` 清洗 |
| `report_context` | `{}`（降级，字段保留） |
| `report_history` / `report_histories` / `report_placements` | 不变（本就走业务表） |
| `runtime_trace` | `{}`（降级，字段保留；前端 `addRuntimeTrace` 空值容错在实现任务中核实，若不容错则改为不返回该字段并让前端走既有缺失分支） |
| `id/title/agent_version/updated_at/created_at` | 不变（conversation_meta） |

- 移除 `_get_checkpoint_saver` 及 langgraph checkpoint 读取（v2 开关下也统一切换——v2 runtime 自用 checkpoint 不受影响）。
- 删除会话（`DELETE /conversations/{id}`）：保留现有行为，追加清理 v3 checkpoint——直接 SQL 删除 `v3_checkpoints.db` 中该 thread_id 前缀的键（kv 表键结构 `{session_id}:agent:{agent_id}:agent_state_blobs*` 与 `…_dump_type`），文件不存在或表不存在时静默跳过。

### 4.3 v2 老会话兼容

v2 时期 `conversation_turn`/`report_versions` 就在写 → 老会话在 v3 下照常恢复展示；v2 开关下重载同样走业务表（v2 的 runtime_trace 重载后同样降级为空——统一路径的既定代价）。

## 5. 错误处理

- checkpoint 文件损坏/pickle 版本不兼容：框架 recover 容错（None → 全新状态），续聊降级为"历史可见、上下文重来"，不阻塞。
- `v3_checkpoints.db` 文件/表不存在（删除会话时）：静默跳过。
- 业务表无该 thread 记录但 meta 存在（极老会话）：messages/html_report 为空，行为同现状的"checkpoint 缺失"分支。

## 6. 测试策略

- 离线单测：`init_v3_checkpointer` 的 conf 正确性（monkeypatch factory）；重载组装的纯函数（业务表 fixture → 响应 dict，内存 SQLite 业务库）；删除会话的 v3 checkpoint 清理（临时 SQLite 文件）。
- **关键离线集成**：真实 `PersistenceCheckpointer` + 临时 SQLite 文件——run 一轮（mock/假 LLM）→ 抛弃实例、新建同 thread_id 会话 pre_run → 断言业务键与消息上下文恢复。
- 联调清单：① 重启服务后续聊（引用重启前上下文）；② 刷新恢复消息列表+报告卡片（含多版本）；③ 删除会话（meta + v3 checkpoint 都清）；④ v2 老会话在 v3 下恢复；⑤ `AGENT_V3_ENABLED=false` 回归（v2 重载也走业务表）；⑥ 审批挂起中重启 → 历史可见、可继续对话（审批作废，预期行为）。

## 7. 风险

1. **pickle 绑定框架内部结构**：openjiuwen 升级后旧 blob 可能反序列化失败——框架容错兜底为"上下文重来"；升级 openjiuwen 版本时须重验（沿用钉版策略）。
2. **conversation_turn 的 assistant_response 完整度**：`finish_turn` 写的是 `final_values["final_response"]`——v3 runtime 当前传 `{"final_response": ""}`（沿袭 v2），重载后 AI 消息可能为空。**实现时须先把 done 帧的 final_response 接进 finish_turn**（v2/v3 runtime 同步改，v2 也受益）。
3. **DbBasedKVStore 的表结构**：框架自建 kv 表（实现时核实表名与建表时机——是否首次写入自动 CREATE TABLE，需纳入接线验证）。

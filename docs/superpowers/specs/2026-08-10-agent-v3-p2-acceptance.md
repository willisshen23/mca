# agent_v3 P2 实机联调验收记录

> 日期：2026-08-10
> 依据：`2026-08-09-agent-v3-p2-persistence-design.md` §6 联调清单；实施记录 `2026-08-09-agent-v3-p2-implementation.md`
> 环境：backend 本地 uvicorn（`AGENT_V3_ENABLED=true/false` 双模式，openjiuwen==0.1.16.post2，deepseek-v4-flash）+ 前端 dev(:3000)
> 结论：**6 项全部通过；期间发现 1 个联调 bug（审批挂起跨重启吞消息），已修复并有回归测试**

## 逐项结果

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 重启服务后续聊 | ✅ | 第一轮记暗号「蓝鲸4277」→ kill 进程重启 → 第二轮准确回忆；`data/v3_checkpoints.db` kv_store 有该 thread 的 pickle blob（2314B） |
| 2 | 刷新恢复消息+报告卡片（多版本） | ✅ | 生成报告 → modify_report 改标题出 v2 → 重启后 `GET /conversations/{id}`：html_report=v2 新标题（1MB blob 还原）、report_histories versions=[1,2]、placements 锚定 user_turn 3/4；前端刷新消息列表与 v1 报告卡片原位恢复（用户目视确认） |
| 3 | 删除会话清理 | ✅ | DELETE 后 conversation_meta=0、v3_checkpoints.db 该 thread 键=0 |
| 4 | v2 老会话在 v3 下恢复 | ✅ | v2 模式造的会话，`AGENT_V3_ENABLED=true` 重启后消息完整恢复 |
| 5 | `AGENT_V3_ENABLED=false` 回归 | ✅ | **把 `data/checkpoints.db` 整个移走后** v2 重载仍返回完整消息——严格证明重载不再依赖任何 checkpoint（事后已恢复原文件） |
| 6 | 审批挂起中重启 | ✅（修复后） | 见下「联调 bug #1」。修复后：重启 → 新消息正常被回答（不再被吞、不再误弹旧审批），历史可见可续聊；进程内待决审批 resume 不受影响 |

## 联调 bug #1：审批挂起跨重启，第一条新消息被"吞"

**现象**：审批挂起中重启服务后，用户发新消息，该消息没有 AI 回复（前端表现为气泡悬空）。

**根因（两段）**：
1. 框架从 checkpoint 恢复了 `__react_agent_interruption__` 中断现场，`react_agent` 主循环见残留即走中断恢复分支——新消息被塞入 `INTERACTIVE_INPUT` 而非对话上下文，旧审批被重新弹窗（消息丢失）。实测还发现：此时 resume 新弹窗可真实执行——**"审批跨重启恢复"其实框架自带**，但与设计预期（审批作废）相比会吞消息，不可取。
2. 直接作废中断后仍 400：中断时上下文最后一条是带 `tool_calls` 的 assistant 消息、无对应 tool 结果，OpenAI 协议拒绝（`tool_calls must be followed by tool messages`）。

**修复**（[sessions.py](../../../backend/src/agent_v3/sessions.py) `prepare_fresh_run_session`，runtime 新一轮 run 且进程内无待决审批时调用）：
- 提前 `session.pre_run()` recover（幂等，Runner 内跳过）→ 清 `__react_agent_interruption__`（同框架 `_clear_interruption_state` 方式）→ 审批作废；
- `repair_dangling_tool_calls`：为每个悬空 tool_call_id 在其归属 assistant 消息后补一条合成 `ToolMessage`（"该操作未执行（审批在服务重启前未完成，已作废）"），协议完整且模型知晓操作未执行；**每次 fresh run 都检查**（兼容老版本落库的遗留损坏上下文）。

**回归测试**：`tests/agent_v3/test_v3_persistence.py::test_prepare_fresh_run_session`（真实 PersistenceCheckpointer + 临时 SQLite：残留中断 + 悬空 tool_call 落库 → 全新实例 prepare → 断言作废、修补、业务键无损、二次 prepare 幂等）。

**验证**：干净复测两轮——① 遗留损坏线程（老代码落库）：修补 count=1 后正常作答；② 全新"审批挂起→重启→发新消息"：作废+修补日志齐出，模型正确回答上下文问题；③ 进程内审批 approve 回归正常，未误作废。

## 全量测试

300 passed + 2 failed（`test_tools_report_export` 两例为 M3 既有问题，非回归，签名与变更前一致）。

## 遗留说明

- 审批挂起重启后按设计**审批作废**：被中断的写工具不会执行（上下文中留有"未执行"合成 tool 消息，模型可见）。若未来想要"审批跨重启可恢复"，框架能力已在（本次实测可恢复可执行），只需产品层面决策 + 前端配合，运行时无需再改。
- `runtime_trace`/`report_context` 重载后为空为设计内降级，字段保留前端无异常。

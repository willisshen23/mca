# agent_v3 P1 实机联调验收记录

> 日期：2026-08-07 ~ 2026-08-09
> 依据：`docs/superpowers/plans/2026-08-07-agent-v3-openjiuwen-p1.md` Task 11 清单
> 环境：backend（`AGENT_V3_ENABLED=true`，openjiuwen==0.1.16.post2，deepseek-v4-flash 端点）+ 前端 dev
> 结论：**12 项全部通过，P1 可收口；期间发现 5 个联调 bug 均已修复并有回归测试**

## 逐项结果

| # | 验收项 | 结果 | 备注 |
|---|---|---|---|
| 1 | 纯问答 | ✅ | done 帧 final_response 正常 |
| 2 | 查询工具 | ✅ | search_activities running/done 帧成对，tool_calls_count=1 |
| 3 | 审批 approve | ✅ | 弹窗工具名/参数/活动名解析正常（bugfix #4 后），确认后队列真实写入 |
| 4 | 审批 edit | ✅ | edited_args 经 `ApproveResult.new_args`（JSON 字符串）真实生效 |
| 5 | 审批 reject + 二次审批 | ✅ | reject 后模型按 feedback 重试→再次弹窗→再 reject 正常收尾，工具未执行 |
| 6 | generate_report 全流程 | ✅ | 管线步骤帧顺序到达、工具帧抑制、报告落库展示、report_updated=true（bugfix #3 后） |
| 7 | export_report | ✅ | done 帧 export_artifact.download_url 可下载 |
| 8 | 取消 | ✅ | approve 后长 LLM 调用期间点停止，0.5s 内 cancelled（bugfix #5 后） |
| 9 | 断线重连 | ✅ | 进行中断网后 `/runs/{tid}` + `/runs/{tid}/stream?after=N` 续接，帧游标连续 |
| 10 | 同会话多轮 | ✅ | 第二轮可引用首轮上下文，会话状态经 checkpointer 恢复（bugfix #2 后） |
| 11 | 刷新降级 | ✅ | 历史消息/报告卡片不恢复（**P1 已知取舍，P2 持久化修复**），可继续对话 |
| 12 | v2 回归对照 | ✅ | `AGENT_V3_ENABLED=false` 重启后 1/3/6 走 v2 路径正常，互不影响 |

## 联调发现并已修复的 5 个 bug（均有回归测试）

| # | 现象 | 根因 | 修复 commit |
|---|---|---|---|
| 1 | 首次 run 即 AttributeError 'NoneType'.id | `create_agent_session` 未传 `card`，in-memory checkpointer 的 pre_agent_execute 需要 agent_id() | `ff61d58` |
| 2 | 第二轮对话 StreamQueue is already closed | AgentSession 实例一次性（post_run 关闭流队列），不能复用；状态连续性靠 checkpointer 按 session_id 恢复 | `08d00ff` |
| 3 | 报告出来了却又冒出"超时 300 秒"消息 | openjiuwen 默认单次工具调用 300s 超时（`DEFAULT_TOOL_CALL_TIMEOUT`），generate_report 实测 361s 被杀（to_thread 管线继续跑完） | `59e82c3`（resilience timeout_s=1200） |
| 4 | 审批弹窗"无参数"+兜底文案 | `__interaction__` 帧请求内容在 `InteractionOutput.value`（误取 `.payload`） | `43a4b8a` |
| 5 | 长 LLM 调用期间停止按钮无响应 | 取消只在流帧间隙检查（无帧即无机会）+ resume 沿袭 v2 不注册取消 | `94ef66e`（泵+0.5s 轮询；resume 注册取消，**刻意偏离 v2**） |

## 新记录的框架坑（P2/P4 注意）

- openjiuwen import 时 `load_dotenv(override=True)` 把 cwd 的 `.env` 写进 `os.environ`（shell 同名变量被 .env 覆盖；测试须 delenv 密封）
- `@tool` 的 description 在 docstring 首个空行截断 → 工具壳 docstring 一律无空行单段
- `DEFAULT_TOOL_CALL_TIMEOUT=300s`（env 可调），长工具须 `card.properties["resilience"]["timeout_s"]`，硬上限 3600s
- `ModelRequestConfig` 字段是 `model_name`（`model` 仅为 alias）
- 工具内 `get_current_session()` 状态方法是 `get_state/update_state`（不是 get_global_state）

## P1 已知取舍（转 P2/P3）

1. **会话重载降级**：刷新后历史消息/报告卡片不恢复（conversations.py 读 langgraph checkpoint，v3 无）→ P2 持久化（SQLite/MySQL checkprovider + 重载链路重写）。
2. **分层模型路由未迁**：v3 固定主模型（cheap/fallback 为成本优化，单独立项）。
3. **报告管线 9 节点**：已是纯函数编排，P1 原样复用；P3 迁 Workflow 摘除 langgraph。
4. 小项（ledger 挂账）：`_skip_tool` 并行批内串扰（窗口极窄）、stale pending interrupt 清理、`_counts` LRU、openjiuwen 导入 ~7s 噪音、resume 可取消（改进项，v2 不可）。

## 测试基线

- v3 套件 53 例全绿（离线）；v2 回归 114 passed + 2 例 M3 既有失败（test_tools_report_export，基线一致）

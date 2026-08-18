# agent_v3 P3 实机联调验收记录：依赖摘除与 v2 退役

> 日期：2026-08-11
> 依据：`2026-08-10-agent-v3-p3-dependency-removal-design.md` §6；计划 `docs/superpowers/plans/2026-08-10-agent-v3-p3-dependency-removal.md` Task 12
> 环境：backend 本地 uvicorn（v3 唯一运行时，openjiuwen==0.1.16.post2，deepseek-v4-flash）+ mock 营销接口(:8005) + 前端 dev(:3000)
> 结论：**API 级 8 项全部通过；全分支终审发现 3 个问题（C1/I1/I2）已修复并经实机验证；待用户前端目视确认后收口**

## 终审（opus 全分支审查）发现与修复

| # | 问题 | 修复 | 实机验证 |
|---|---|---|---|
| C1 | 管线 seed 改 dict 消息后，`template_matching._latest_user_text` 仍按对象取 `.content`——默认报告路径必崩 | dict 感知取值（commit `60978ea`），含全管线清扫 | ✅ 报告全流程跑通 |
| I1 | openjiuwen 共享 HTTP 客户端缓存键不含 timeout，主 agent 先建客户端（120s）导致管线 LLM 超时从 600s 静默降为 120s | `GuardedModel.invoke` setdefault 默认超时（`60978ea`） | ✅ 合成调用耗时 141.8s 成功（修复前必超 120s 失败） |
| I2 | 共享 httpx 客户端跨事件循环复用（主循环建、worker 线程管线用）风险 | 实机验证无异常，不加 kill-switch | ✅ 主循环对话后立即跑管线正常 |
| M2 备忘 | 主对话模型 token 用量不落库（P2 起既有，设计内） | 不处理 | — |

## 逐项结果（API 级）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 纯问答 / 查询工具 | ✅ | search_activities 返回 20 条活动，帧契约不变 |
| 2 | 审批 approve | ✅ | add_to_analysis_queue / modify_report 两次 approve 均真实执行 |
| 3 | generate_report 全流程 | ✅ | **7 个管线步骤帧 running/done 成对、中文进度文案完整**（writer 显式注入替代 patch hack 后无回归）；html_guard 通过；v1 落库 |
| 4 | modify_report | ✅ | GuardedModel（temperature=0.2）改标题出 v2 |
| 5 | export_report | ✅ | export_artifact.download_url 正常 |
| 6 | LLM 日志与用量落库 | ✅ | `[LLM]` 请求/返回日志齐；llm_token_usage_logs 新增 SUCCESS 行（合成 32683 tokens / 141.8s，修改 7934 tokens） |
| 7 | 重启续聊 + 刷新恢复 | ✅ | 重启后重载：10 条消息、html_report=v2 新标题、versions=[1,2]、placements 锚点正确；上下文回忆准确（答出改后标题） |
| 8 | 框架残留清零 | ✅ | `grep langchain/langgraph/deepagents src/` 零命中；`import src.main` OK |

未覆盖项及依据：审批 edit/reject（P1 已验，rails 代码 P3 未动）；取消/断线重连（P1/P2 已验，runtime 缓冲与泵逻辑 P3 未动，仅 import 来源变化）。

## 测试

全量 301 passed + 2 failed（test_tools_report_export 两例 M3 既有问题，签名不变）。P3 期间新增：llm 工厂 9 例、impl 契约 5 例、壳层契约重写、dict 消息回归 7 例、persistence 1 例（P2）等。

## 部署警告（必须随版本发布说明）

1. **`AGENT_V3_ENABLED` 已从配置删除——旧 .env 残留该键会导致启动失败**（pydantic-settings dotenv 默认 extra=forbid → ValidationError），部署前必须从环境文件中删除该键。
2. **requirements-offline.txt 尚未包含 openjiuwen**（P4 离线打包范围）——本分支不可用于离线环境发版，P4 完成前不得出离线包。
3. `data/checkpoints.db`（v2 langgraph checkpoint）成为历史文件，代码不再读写，可保留归档。

## 待用户目视

前端 http://localhost:3000，user_id `p3test`，会话「P3验收」：刷新后消息列表 + 两张报告卡片（v1/v2）原位恢复、报告渲染正常。

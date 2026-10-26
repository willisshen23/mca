# openJiuwen 框架应用经验总结（培训材料）

> 整理自营销活动分析助手项目 agent_v2（langgraph/deepagents）→ agent_v3（openJiuwen agent-core）的完整迁移实践。
> 素材来源：`backend/src/agent_v3/` 源码、`docs/superpowers/specs/` 下 9 份迁移调研/实施/验收文档。
> 框架版本：`openjiuwen==0.1.19.post2`，Python 3.12，行内 deepseek-v4-flash 端点。

---

## 一、openJiuwen 是什么

- 华为云 AgentArts 的开源版（2025-12 开源），**agent-core 是其 Python SDK 核心引擎**。
- License：**Apache-2.0**；Python 要求 **>=3.11, <3.14**；安装 `pip install -U openjiuwen`。
- 仍是 **0.1.x**（迭代极快，0.1.x 已发 25+ 个版本）——**钉版策略是硬性要求**。
- 核心能力一览：
  | 能力 | 入口 |
  |---|---|
  | 智能体 | `ReActAgent` + `Runner.run_agent / run_agent_streaming`（思考→行动→观察循环） |
  | 工具 | `@tool` 装饰器 / `RestfulApi` / `MCPTool` 三种形态 |
  | HITL | Rail 拦截器（`ConfirmInterruptRail` / 自定义 `BaseInterruptRail`） |
  | 工作流编排 | `Workflow` + 组件 + `BranchComponent` 条件分支 |
  | 多智能体 | AgentAsTool（子 Agent 作为工具）、TeamRuntime |
  | 持久化 | `CheckpointerFactory` 可插拔；内置 in_memory 与 `PersistenceCheckpointer`（SQLite/MySQL 通道） |
  | 模型接入 | `ModelClientConfig` + `ModelRequestConfig`，内置 OpenAI 兼容协议（可指任意 api_base） |
  | 可观测 | 内置全链路 tracer |

---

## 二、项目中怎么用：agent_v3 架构

agent_v3 是**唯一运行时**（agent_v2 已整体删除；URL 前缀 `/api/v2/agent/*` 仅为前端契约保留，SSE 帧契约不变，前端零改动）。全仓库只允许 `agent_v3` 包内 import openjiuwen。

```
Vue 前端 ──SSE──> FastAPI 路由(agent_v2.py) ──> agent_v3/runtime.py
                                                    │
                              ┌─────────────────────┼──────────────────────┐
                              ▼                     ▼                      ▼
                     agent_factory.py         sessions.py            events/sse_bridge.py
                     ReActAgent 单例          每轮新建 AgentSession   OutputSchema→SSE 帧
                     + 4 个 Rail              + PersistenceCheckpointer + _BufferedRun 断线重连
                              │
                              ▼
                     13 个 @tool 业务工具（壳）→ tools/impl/*（无框架依赖业务实现）
```

### 2.1 Agent 组装（agent_factory.py）

进程级单例 + asyncio.Lock 双重检查：

```python
client_cfg = ModelClientConfig(
    client_provider="OpenAI",          # OpenAI 兼容协议，api_base 可指任意端点
    api_key=..., api_base=...,
    timeout=120, max_retries=..., verify_ssl=...,
)
request_cfg = ModelRequestConfig(model=..., temperature=...)
context_engine_config, context_processors = build_v3_context_configs(
    settings, client_cfg, request_cfg,
)

agent = ReActAgent(card=AgentCard(id="activity-analysis-marketing-agent-v3", description="..."))
       .configure(ReActAgentConfig(
           model_config_obj=request_cfg,
           model_client_config=client_cfg,
           prompt_template=[{"role": "system", "content": build_system_prompt()}],
           max_iterations=settings.agent_v3_max_iterations,   # 默认 5 太小，显式调大（本项目 50）
           context_engine_config=context_engine_config,
           context_processors=context_processors,
       ))
agent.set_llm(LoggingModel(client_cfg, request_cfg, label=...))  # 鸭子类型包装，打 io 日志

for t in ALL_V3_TOOLS:                    # 工具双注册
    Runner.resource_mgr.add_tool(t)
    agent.ability_manager.add(t.card)

# 注册 Rail（顺序敏感）
await agent.register_rail(ApprovalEditRail(tool_names=WRITE_TOOLS))
await agent.register_rail(ApprovalEditRail(tool_names=["generate_report"], require_existing_report=True))
await agent.register_rail(UnknownToolGuardRail(...))
await agent.register_rail(ToolCallLimitRail(...))
await agent.register_rail(ToolProgressRail(...))
```

要点：
- `prompt_template` 用消息列表形式注入系统提示词；系统提示词支持管理后台 DB 覆盖 + 8 条关键规则幂等追加。
- `LoggingModel` 刻意用**鸭子类型包装**而非继承 `Model`——框架会探测 `supports_kv_cache_release` 等能力方法，继承而不调 `super().__init__` 会 AttributeError。
- 主对话启用原生 `MessageOffloader` → `DialogueCompressor` 处理器和 20 轮滑窗；大 tool 消息写入专用 workspace 并保留带精确 path 的 reload marker，模型通过原生 `read_file` 按需恢复，沙箱只允许读取该目录。历史工具型 ReAct 块由主模型生成摘要。阈值与开关走 `AGENT_V3_CONTEXT_*`，不配置消息数硬上限，checkpoint 保存处理后的上下文。

### 2.2 HITL 审批：自定义 Rail 实现 approve/edit/reject 三决策

不用框架现成的 `ConfirmInterruptRail`，而是继承 `BaseInterruptRail`（rails.py）：

```python
class ApprovalEditRail(BaseInterruptRail):
    async def resolve_interrupt(self, ctx, user_input):
        if user_input is None:                       # 首次触发 → 挂起
            return self.interrupt(InterruptRequest(message=..., payload_schema=APPROVAL_PAYLOAD_SCHEMA))
        decision = user_input.get("decision")
        if decision == "approve":
            return self.approve()
        if decision == "edit":                        # 改写参数后放行
            return self.approve(new_args=json.dumps(edited_args))
        # reject：以 ToolMessage 形式回传模型继续规划，而非抛异常
        return self.reject(tool_result="用户拒绝了本次操作。用户反馈：…请尊重用户决定…")
```

- **条件审批**：`require_existing_report=True` 实例仅当会话已有 `html_report` 才中断（generate_report 覆盖确认场景），否则直接 approve。
- 审批恢复：前端 → `InteractiveInput().update(interrupt_id, payload)` → 同 session 再次 `run_agent(_streaming)`。
- 审批文案双层：框架侧固定模板 + LLM 生成口语化副标题（轻量模型，5s 超时/失败均回退模板文案）。

### 2.3 会话与持久化

- **Checkpointer**：框架自带 `PersistenceCheckpointer`（不是自研！），SQLite 后端：

  ```python
  checkpointer = await CheckpointerFactory.create(
      CheckpointerConfig(type="persistence", conf={
          "db_type": "sqlite", "db_path": str(db_path),
          "db_timeout": 5, "db_enable_wal": True}))
  CheckpointerFactory.set_default_checkpointer(checkpointer)  # 必须在 Runner.start 之前
  ```

  conf 预留 MySQL 通道（`db_client` 传预构 AsyncEngine）。v3 用独立文件 `data/v3_checkpoints.db`。

- **会话生命周期**：`AgentSession` 实例是**一次性的**（post_run 关闭流队列，复用会报 `StreamQueue is already closed`）。每轮 run 都 `create_agent_session(session_id=thread_id, card=card)` 新建，状态连续性靠 checkpointer 按 session_id 恢复。`card` 必传，否则 pre_run 报 AttributeError。

- **分层持久化核心原则**（背下来）：
  > **checkpoint blob 只有框架自己读写（续聊状态），应用层重载只读业务表（展示历史）。**

  会话重载接口走业务表（conversation_turn / report_versions），v2/v3 通吃，不读任何 checkpoint——已实测"把 checkpoints.db 整个移走后重载仍返回完整消息"。

### 2.4 流式输出 → SSE 桥接

- 入口：`Runner.run_agent_streaming(..., stream_modes=[OUTPUT, CUSTOM])`——**CUSTOM 模式必须显式传**，否则工具内 `write_custom_stream` 的自定义帧出不来。
- 实测帧类型映射表：

  | 框架帧 | 含义 | 桥接为 |
  |---|---|---|
  | `llm_output` | 正文 token 增量 | 正文增量帧 |
  | `llm_reasoning` | 思考增量 | 思考帧（可折叠） |
  | `answer` | 最终聚合完成帧 | done 帧（注意 `result_type=="error"` 是框架吞掉的异常，必须 raise） |
  | `__interaction__` | 中断/审批请求 | `approval_required` 审批卡片帧 |
  | `llm_usage` / `tracer_agent` | 用量 / 链路追踪 | 落库 / 忽略 |
  | CustomSchema（`activity-analysis` marker） | 工具进度 / 状态更新 | node_update / state_update 帧 |

- **断线重连**：`_BufferedRun` 缓存帧 + 游标重放（`GET .../stream?after=N`），服务端权威 `pending_approval` 状态供前端刷新后作废本地残留审批卡片。
- **取消**：泵任务 + 0.5s 轮询 `is_cancelled()`（长 LLM 调用期间无帧也能生效），退出时 `pump.cancel()` 把 CancelledError 传播进在途调用。

### 2.5 业务工具改造：壳/impl 分层（最值得借鉴的模式）

13 个工具，每个都是 `@tool` 装饰的 **async 壳函数**，壳只做三件事：组装 ToolContext → 调 impl 业务函数（**无框架依赖**）→ 把 state_updates 写回会话：

```python
@tool
async def search_activities(keyword: str = "", ...) -> str:
    """按关键词/渠道/日期等条件查询银行营销活动..."""   # docstring 即工具描述
    return await _run(impl_activity_query.search_activities, dict(...))
```

- **敏感参数（user_id/org_no/channel/file_path）绝不让 LLM 生成**：不在工具签名里（对模型不可见），走 ContextVar 注入——主通道是 runtime 每轮 `set_request_context`，兜底通道是独立 ContextVar 供 `asyncio.to_thread` 线程里的代码读。
- 框架无关的 impl 层 = 换框架时只需重写壳层，也是本次从 langchain 工具迁过来的成本大头被削掉的原因。
- 长工具超时：`_t.card.properties["resilience"]["timeout_s"] = 1200`（框架默认 300s 会杀 generate_report，实测 361s）。

### 2.6 自研 Rail 防线（框架没有的能力）

| Rail | 作用 |
|---|---|
| `ApprovalEditRail` | HITL 三决策审批（见 2.2） |
| `ToolCallLimitRail` | 每轮工具调用上限（默认 8），**按 session_id 隔离计数**（agent 是单例，防并发会话互吃额度）；超限置 `ctx.extra["_skip_tool"]` + 写 ToolMessage 让模型收尾 |
| `UnknownToolGuardRail` | 幻觉工具拦截——框架对未注册工具只回 "Ability not found" 且继续循环，需主动返回合法工具清单纠正 |
| `ToolProgressRail` | 框架流式无工具开始/结束帧，用 `session.write_custom_stream` 自发进度帧；还要区分审批中断/审批拒绝避免误发 done 帧 |

### 2.7 模型层

- 角色化工厂 `get_model(role)`：每个角色可独立配 `{role}_llm_api_key/base_url/model/temperature`，缺省回退全局 `llm_*`。
- 每次调用包 `GuardedModel`：token 预算守卫（超限抛 `ModelContextLengthExceeded`）+ io 日志 + 用量落库。
- API key 支持 `enc:v1:` 密文，加载时解密。

---

## 三、迁移方法论（怎么把风险控制住）

**先 spike → 分阶段替换 → 每阶段实机验收 + 回归测试网 → 终审再抓一轮。**

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0 spike（1~2 天）** | 只验三件事：① 行内端点 OpenAI 兼容 + tool calling；② ReActAgent + 写工具 + Rail 走完 interrupt→resume 全流程；③ 流式可桥接 SSE。**任何一条不过即中止，成本可控** | 3 项 + 附加项全 PASS |
| **P1 替换对话运行时** | agent_v3 包并行新建不动 v2；双开关切换 | 12 项实机联调全过，5 个联调 bug 修复+回归；v3 套件 53 例全绿 |
| **P2 持久化** | PersistenceCheckpointer 接线 + 业务表重载重写 | 重启续聊实测（记暗号→kill→重启→准确回忆）；300 例测试 |
| **P3 摘除旧依赖** | 删 langgraph/langchain/deepagents 全系 8 条依赖，LLM 层也迁 openjiuwen Model，v2 退役 | grep 零命中；终审再抓 3 个问题修复 |
| **P4 离线打包** | 全量闭包 wheel 集 + 断网安装验证 | 断网安装 + 业务冒烟全过；包 260M / wheels 161 个 |

关键实践：
- **P0 spike 必须先跑一手结论**，官方文档没覆盖的（max_iterations 上限、token 流在 interrupt 前后的完整性）必须在 spike 实测。
- **并行新建 + 开关切换**，旧链路随时可回退，全部验收过了再删旧代码。
- **接口钉版**：0.x 框架迭代极快，requirements 钉死 `openjiuwen==0.1.19.post2`。
- **验证脚本要防假阳性**（见 P4 教训）。

---

## 四、框架特有的坑与解决办法（按主题整理，全部实机验证过）

### 4.1 Agent 配置与生命周期

1. **`max_iterations` 默认 5 太小**：多工具编排场景工具执行完无剩余迭代生成答复，返回 error。必须显式调大（本项目 50）。
2. **`AgentSession` 一次性**：不能复用实例，状态连续性靠 checkpointer；组装时 `card` 必传。
3. **openjiuwen import 时 `load_dotenv(override=True)`**：把 cwd 的 `.env` 覆盖写进 `os.environ`（shell 同名变量被覆盖）；测试须 delenv 密封。
4. **重复注册同名工具**到 `Runner.resource_mgr` 会打 ERROR 日志（不影响运行）——进程级单例只注册一次。

### 4.2 工具

5. **`DEFAULT_TOOL_CALL_TIMEOUT=300s`**：长工具必须 `card.properties["resilience"]["timeout_s"]`，硬上限 3600s。否则 to_thread 里的管线变孤儿（框架杀了调用但线程还在跑）。
6. **`@tool` 的 description 在 docstring 首个空行截断** → 工具壳 docstring 一律无空行单段。
7. 注解坑消失：`from __future__ import annotations` 下 `@tool` schema 抽取正常（langchain 时代的坑在 agent-core 不存在）。
8. **每轮工具调用上限无内置配置** → 自定义 Rail 计数；注意模型收到"超限"ToolMessage 后会重试（实测 rail 观测到 5 次意图），skip 文案必须明确"不要再调用"。

### 4.3 HITL

9. **reject 后模型可能重试同一工具 → 再次 interrupt（二次审批）**：前端审批 UI/状态机必须支持"同一轮多次审批"，能区分"同一 tool_call 的二次审批"。
10. **审批挂起中重启服务会吞新消息**（P2 最难的 bug）：重启后框架从 checkpoint 恢复 `__react_agent_interruption__` 残留现场，把新消息塞进 INTERACTIVE_INPUT 而非对话上下文。修复：fresh run 前 `pre_run()` recover → 清残留中断（审批按设计作废）→ `repair_dangling_tool_calls` 为悬空 tool_calls 补合成 ToolMessage（否则 OpenAI 协议 400：`tool_calls must be followed by tool messages`）。
11. **`__interaction__` 帧的请求内容在 `InteractionOutput.value`**，不是 `.payload`。
12. 遗留资产：**"审批跨重启恢复"框架其实自带**（实测可恢复可执行），本项目按设计作废；未来若要启用只需产品决策 + 前端配合，运行时无需再改。

### 4.4 模型层

13. **进程级共享 HTTP 客户端不能跨事件循环使用**：报告管线在独立线程的 `asyncio.run` 中结束并关闭事件循环后，主 Agent 再复用共享连接会报 `Event loop is closed` / `APIConnectionError`。项目统一配置 `use_shared_llm_http_client=False`，每次请求创建并关闭独立客户端；逐请求超时通过 `invoke(timeout=...)` 传递。
14. **`ModelRequestConfig` 字段是 `model_name`**（`model` 仅为 alias）。
15. 框架把底层异常包成 `FrameworkError`，原始 openai 异常在 `__cause__` 链上。
16. 工具内取会话状态是 `get_current_session().get_state/update_state`（不是文档里的 `get_global_state`）。

### 4.5 持久化

17. **`CheckpointerConfig` 不在 `openjiuwen.core.session.checkpointer` 包导出里**，需从 `.checkpointer.checkpointer` 子模块导入。
18. agent state 整体 **pickle** 序列化 → **绑定框架内部结构：升级 openjiuwen 版本后旧 blob 可能反序列化失败**。框架容错为"上下文重来"（不抛错），历史展示因走业务表不受影响——但升级版本必须重验（钉版策略的原因之一）。
19. SQLite 走 `sqlite+aiosqlite` + WAL + DbBasedKVStore，kv_store 表自动建表。

### 4.6 流式与取消

20. **提前 break 消费流触发 ContextVar 警告**（"created in a different Context"，框架已知模式）；完整消费无此问题；取消按泵取消 + `agen.aclose()` 处理，不要依赖流间隙检查（长 LLM 调用期间无帧 → 停止按钮无响应）。

### 4.7 依赖与离线交付

21. **依赖体量大**（80 项：transformers/pymilvus/trafilatura/fastmcp/dashscope 等）：既定决策**全量闭包下载不裁剪**；`pip download --only-binary=:all:` 遇无 wheel 包的应对顺序：① 换有 wheel 的兼容版本并钉版（记录原因）② 万不得已才单包 sdist（目标机无编译链）。
22. **cryptography 50.0.0 无 macOS x86_64 wheel**（源码编译需 Rust）：必须先行钉版 `cryptography==46.0.7` 并写入离线约束文件。
23. **断网安装铁证**：容器 `--network none` 断网安装 + import 冒烟 = wheel 闭包自洽，不依赖 pip 解析器承诺。
24. **CA 兜底**：openjiuwen 严格 SSL 校验走系统 CA，CA 不全的目标机上 LLM 调用全部 `CERTIFICATE_VERIFY_FAILED` → 启动脚本内置 `SSL_CERT_FILE=certifi` 兜底。
25. **验证脚本防假阳性**（P4 两个真实教训）：verify.sh 缺 `docker run -i` 导致 heredoc 没送进容器、脚本空跑仍输出 VERIFY-PASS；`-e EXPECTED_ASSET` 未 export 导致前端新鲜度断言被静默跳过。**断言不可静默跳过**。

### 4.8 配置与部署

26. **删除的配置键必须从旧 .env 清除**：`AGENT_V3_ENABLED` 删除后旧 .env 残留会导致启动失败（pydantic-settings dotenv 默认 extra=forbid → ValidationError）——此类变更必须随版本发布说明。

---

## 五、可复用的适配模式清单

| 模式 | 用途 |
|---|---|
| **壳/impl 分层** | `@tool` 壳只管框架交互，业务实现零框架依赖——换框架只换壳 |
| **ContextVar 双通道注入敏感参数** | user_id/org_no 不进 LLM 上下文，工具内从 ContextVar 读 |
| **自定义 Rail 三件套** | 审批（BaseInterruptRail）、限额/护栏（AgentRail.before_tool_call + `_skip_tool`）、进度帧（write_custom_stream） |
| **鸭子类型包装 Model**（LoggingModel/GuardedModel） | 加日志/token 守卫而不触发框架能力探测坑 |
| **分层持久化** | checkpoint blob 只框架读写（续聊），业务表驱动重载（展示） |
| **`asyncio.to_thread(lambda: asyncio.run(...))`** | 同步 DB/HTTP 的管线在 worker 线程独立事件循环跑，不进主循环 |
| **_BufferedRun + 帧游标** | SSE 断线重连、刷新后服务端权威状态对账 |
| **角色化模型工厂 + 密文 API key** | 多模型路由、密钥不落明文 |

---

## 六、一句话总结

> openJiuwen 的 HITL/流式/持久化三大核心机制与主流 Agent 框架有一一对应物，**核心机制迁移不难，难的是四处胶水层**（审批 edit 决策、会话重载、context 注入、多模型路由）；用"先 spike、分阶段、每阶段实机验收"的方法论可以把 0.x 框架的不确定性关在笼子里。

---

## 附：关键源码位置速查

| 主题 | 文件 |
|---|---|
| Agent 组装 | `backend/src/agent_v3/agent_factory.py` |
| 审批/限额/幻觉/进度 Rail | `backend/src/agent_v3/rails.py` |
| LLM 审批话术 | `backend/src/agent_v3/approval_wording.py` |
| 会话生命周期/中断作废修补 | `backend/src/agent_v3/sessions.py` |
| Checkpointer 接线 | `backend/src/agent_v3/state/persistence.py` |
| SSE 桥接/断线重连/取消 | `backend/src/agent_v3/runtime.py`、`events/sse_bridge.py` |
| 工具壳层 | `backend/src/agent_v3/tools/__init__.py` |
| 业务实现（无框架依赖） | `backend/src/agent_v3/tools/impl/*.py` |
| 模型工厂/守卫/日志 | `backend/src/llm.py` |
| 迁移调研与 P0 spike | `docs/superpowers/specs/2026-08-07-openjiuwen-*.md` |
| 各阶段设计/验收 | `docs/superpowers/specs/2026-08-0x-agent-v3-p*.md` |

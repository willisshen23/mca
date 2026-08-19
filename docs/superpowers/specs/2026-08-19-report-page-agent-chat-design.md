# 报告页接入真实智能体对话 — 设计文档

日期：2026-08-19
状态：待评审

## 背景

`/analysis/report`（ReportView.vue）目前是纯 mock 页面：报告内容来自写死的
`ReportSummary` 组件，底部"AI报告问答"只是 setTimeout 假回复。而 `/chat-ui`
（UiChatView.vue，约 3930 行）已经具备完整的真实智能体对话能力：SSE 流式消费、
思考过程面板（execution_trace）、活动选择、报告修改审批、HTML 报告卡片、
导出、断流重连、刷新恢复等。

用户在三步向导中：第一步（SourceConfigView）选择线上活动或上传线下文件；
第二步（SkillComposerView）编排分析组件；第三步进入报告页。前两步的选择
保存在 `analysisStore`（`selectedActivityNames`、`offlineStart/End/uploadDone`、
`canvasComps`）。

## 目标

1. 进入报告页时，把前两步所选数据组装成首条消息，自动调用真实智能体
   （`/v2/agent/run` SSE）开始生成报告。
2. 报告页支持与智能体多轮对话，能力与 chat-ui 完整对齐：流式思考过程、
   审批、报告更新、停止/重连/刷新恢复。
3. 与 UiChatView 共享实现，不复制逻辑：抽取共享 composable / 工具函数 / 组件。

## 已确认的决策

| 问题 | 决策 |
|---|---|
| 对话能力范围 | 完整对齐 chat-ui（思考面板、审批、报告更新、停止等） |
| 页面布局 | 保留现有布局（信息头 + 报告区 + 底部 AI 问答区） |
| 代码复用 | 抽取共享 composable，UiChatView 一并重构 |
| 线下路径 | 顺带把 OfflineSourceConfig 接入真实 uploadFile API |
| 会话策略 | 每次从 compose 进入新建会话重新生成；报告页内刷新则恢复进行中会话 |

## 架构设计

### 共享层抽取（从 UiChatView.vue 拆出）

**纯函数工具**（无状态，直接搬运）：

- `frontend/src/utils/agentTrace.js`：`stepKey`、`traceDisplayName`、
  `TRACE_STEP_ORDER`、`visibleTraceSteps` 及合并分组函数、
  `traceProgressText`、`thinkingTitleText`、`stepStatusText`、
  `isPendingStep`、`shouldDisplayThinkingTrace`、`tracePayloadForStep`、
  `syncTracePlan`、`upsertTraceStep`、`finishThinkingTrace` 等 trace 相关逻辑。
- `frontend/src/utils/activityFormat.js`：`activityName/Id/Period/Tags/Summary/
  RowNumber`、`compactActivity`、`compactTemplate`、`visibleActivities`、
  活动选择（`toggleActivitySelection`、`selectedActivityRowNumbers` 等）。
- `frontend/src/utils/htmlReport.js`：`buildHtmlDocument`、
  `stripReportFooterNote`、iframe resize / PNG 快照桥脚本常量与注入函数。

**状态引擎 composable**：

- `frontend/src/composables/useAgentChat.js`：以一个响应式 conversation 对象
  （`{ id, title, typing, dynamicMessages }`）为核心，封装：
  - `send(text, { filePath, selectedRows, displayText })` — 调 `runAgentV2`
    并消费 SSE 流；
  - `consumeStream(response, options)` — 事件分发：node_update → trace 面板；
    approval_required → 审批卡片；done → AI 消息 / html_report / export artifact；
    error / cancelled；断流重连（`attachAgentV2Run` + run sequence 游标）；
  - `cancel()`、`resolveApproval(message, decision, editedArgs)`（调
    `resumeAgentV2`）；
  - `recover()` — 刷新/恢复进行中的任务；
  - `persist()` / `restore(detail)` — localStorage 压缩持久化 +
    服务端消息/报告历史恢复；
  - 通过 options 注入宿主差异：`scrollBottom`、`urlParams`（userId/orgNo 等）、
    `onHtmlReport(html, payload)` 回调（报告页用它把最新报告同步到报告区）、
    `reportCardMode: 'full' | 'slim'`。

**共享组件**：

- `components/chat/ChatMessageList.vue` — 消息流渲染：user/ai 气泡（markdown）、
  system 消息、execution_trace 思考面板、approval_request 审批卡片、
  typing 动画。UiChatView 与 ReportView 共用。
- `components/chat/HtmlReportCard.vue` — 报告卡片：iframe srcdoc 预览
  （sandbox="allow-scripts"）、全屏 / 下载 PNG / 下载 HTML、点赞点踩反馈、
  版本历史条。支持 `slim` 模式（报告页对话内使用，见下）。
- `components/chat/ChatComposer.vue` — 输入区：textarea（Enter 发送 /
  Shift+Enter 换行）、发送/停止按钮、附件上传、快捷提问 chips、
  已选行 chips、浮动任务进度指示器。

**UiChatView 重构**：改为组装上述 composable 与组件，保留侧边栏会话管理
（列表、新建、重命名、删除、切换），行为对外不变。

### ReportView 改造

保留现有三段式布局：

1. **报告信息头**：展示真实选择数据——活动类型、所选活动名称、周期、
   分析组件 chips（`canvasComps`）。生成时间取会话创建时间。
2. **报告区**（替换 mock `ReportSummary`）：iframe 渲染最新 `html_report`
   （复用 `buildHtmlDocument` + resize 桥，自动撑高、有上下限）。生成中显示
   骨架/进度占位（可取当前 trace 进度文案）。智能体修改报告产生新版本时
   原地更新 iframe。底部"导出HTML"按钮直接下载当前报告 HTML。
3. **AI 问答区**：`ChatMessageList` + `ChatComposer`，chat-ui 同款交互。
   对话流中的 `html_report` 消息以 **slim 卡片** 呈现（"报告已生成 /
   已更新至 vN，点击查看"——点击滚动到报告区），不与报告区重复渲染整份报告。

### 数据流与自动开始

```
步骤1 analysisStore: selectedActivityNames（线上）
                     或 uploadedFile.file_path + offlineStart/End（线下）
步骤2 analysisStore: canvasComps（分析组件名列表）
        │
        ▼ ReportView onMounted
if localStorage 有本报告页的进行中会话 → restore + recover（刷新场景）
else:
  createConversationAPI() 创建会话
  拼装首条消息（见下）→ useAgentChat.send() → SSE 流式生成
  会话 id + 报告上下文（选择快照）写 localStorage
```

首条消息组装规则（线上示例）：

```
请为以下线上活动生成分析报告：「活动A」「活动B」（周期 2024-01-01 至 2024-03-31）。
分析框架请包含以下组件：组件P、组件Q、组件R。
```

线下示例：

```
请基于上传的活动数据文件「2024线下活动数据.xlsx」（周期 … 至 …）生成分析报告。
分析框架请包含以下组件：…
```

（线下发送时携带 `filePath`，与 chat-ui 上传路径一致。）

localStorage 键：

- `report_page_session` → `{ conversationId, context: {...选择快照}, createdAt }`。
  从 compose 点击"生成分析报告"进入时先清除该键（保证新建）；
  报告页 onMounted 检测到键存在则恢复而非新建。

### 线下上传接入

`OfflineSourceConfig.vue` 的 `toggleUpload` mock 改为真实上传：选择文件 →
`uploadFile()`（`api/files.js`）→ 成功后将 `{ file_name, file_path }` 与
日期范围存入 `analysisStore.state.offlineFile`；`canGoNext` 校验改为依赖
真实上传结果。报告页拼装消息时携带 `filePath`。

### analysisStore 调整

- `offlineFile: null | { file_name, file_path }` 替代 `uploadDone` 布尔；
- 新增 `resetReportSession()` 供 compose 页"生成分析报告"按钮调用
  （清除 `report_page_session`，保证每次新建）。

### 错误处理

- 创建会话 / 发送失败：问答区显示错误消息，报告区占位显示"生成失败，
  可在下方重试"，用户在对话框重新发送即可（消息已入会话）。
- 断流：沿用 chat-ui 的游标重连 + `系统繁忙` 兜底文案。
- 刷新恢复：localStorage 有会话 → 拉取服务端消息与报告历史恢复；
  有进行中任务 → `attachAgentV2Run` 续传。
- 直接进入 `/analysis/report`（未经前两步、也无会话快照）：显示空态提示
  "请先从第一步选择活动"，提供跳转按钮。

## 测试与验证

前端无测试框架，验证方式：

1. `vite build` 通过；
2. UiChatView 回归（抽取后行为不变）：发送消息、思考面板、审批、
   报告卡片、导出、刷新恢复；
3. 报告页走查（Playwright / 手工）：
   - 线上：选活动 → 编排组件 → 进入报告页自动开始生成 → 报告区渲染 →
     追问 → 修改报告审批 → 报告区更新 → 导出 HTML → 刷新恢复；
   - 线下：上传文件 → 进入报告页自动生成；
   - 直接进入报告页的空态。

## 风险

- **UiChatView 重构回归风险**：3900 行组件拆分时保持逐函数搬运、
  先抽纯函数与 composable（验证）再抽组件（再验证），两个阶段分开提交。
- **sse 逻辑耦合宿主**：`consumeAgentStream` 里散落了 scrollBottom、
  pageUnloading 等宿主状态，抽取时统一收进 composable 内部或通过
  options 注入，注意不遗漏。
- **localStorage 体积**：报告页持久化沿用现有 compact 策略
  （html_report 不落盘，从服务端恢复）。

## 实施阶段

1. 阶段一：抽取 `utils/agentTrace.js`、`utils/activityFormat.js`、
   `utils/htmlReport.js` + `composables/useAgentChat.js`；UiChatView 切换，
   行为不变。验证后提交。
2. 阶段二：抽取 `ChatMessageList` / `HtmlReportCard` / `ChatComposer`
   组件；UiChatView 切换。验证后提交。
3. 阶段三：OfflineSourceConfig 接真实上传 + analysisStore 调整。
4. 阶段四：重写 ReportView（信息头真实数据、报告区 iframe、问答区、
   自动开始、刷新恢复、空态）。验证后提交。

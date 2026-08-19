# 报告页接入真实智能体对话 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `/analysis/report` 从 mock 页改造为接入真实智能体（SSE 流式）的报告生成与对话页，与 `/chat-ui` 共享实现。

**Architecture:** 从 UiChatView.vue（3930 行）抽取三层共享代码——纯函数 utils（agentTrace / activityFormat / htmlReport）、状态引擎 composable（useAgentChat）、展示组件（ChatMessageList / HtmlReportCard / ChatComposer）；UiChatView 逐阶段切换验证；最后重写 ReportView：进入页面自动用前两步选择组装首条消息开始生成报告，报告区 iframe 渲染，问答区完整对话能力。

**Tech Stack:** Vue 3 `<script setup>`、Vue Router 4、Vite 5、原生 fetch SSE、vitest + jsdom（新增 devDependency，仅用于纯函数抽取的回归保护）。

**Spec:** [docs/superpowers/specs/2026-08-19-report-page-agent-chat-design.md](../specs/2026-08-19-report-page-agent-chat-design.md)

## Global Constraints

- 前端目录：`frontend/`，所有命令在 `frontend/` 下执行。
- 代码风格：2 空格缩进、单引号、分号结尾，与现有代码一致；UI 文案为中文。
- 不新增运行时依赖；仅新增 devDependency `vitest` 与 `jsdom`。
- 抽取任务的原则是**逐函数原样搬运**（move verbatim），只改 import 与注入点，不改逻辑；每个抽取任务完成后 `npm run build` 必须通过。
- 开发服务器：`npm run dev`（端口 3000），后端已在本机运行。
- 提交信息使用中文短句，与仓库历史风格一致（如 `抽取思维链纯函数到 utils`）。

## 关键背景（执行者须知）

- `frontend/src/views/UiChatView.vue` 是唯一真实对话实现，本计划大量任务是把其中的函数原样移出。行号会随任务推进漂移，**以函数名定位**。
- 会话对象是普通响应式对象：`{ id, title, typing, dynamicMessages, meta, group, agentVersion }`。
- 消息 `role` 类型：`'user' | 'ai' | 'system' | 'execution_trace' | 'approval_request' | 'html_report'`。
- SSE 事件类型：`node_update` / `approval_required` / `done` / `error` / `cancelled`，以 `\n\n` 分块、`data:` 前缀、`id:` 为续传游标。
- 后端接口封装在 `frontend/src/api/`：`agentRun.js`（runAgentV2/resumeAgentV2/cancelAgentV2/getAgentV2RunStatus/attachAgentV2Run）、`conversations.js`（fetchConversations/createConversationAPI/deleteConversationAPI/renameConversationAPI/fetchConversationMessages/getUserId）、`agentRunHistory.js`（submitReportFeedback/reportDownloadUrl）、`files.js`（uploadFile）、`quickPrompts.js`（fetchQuickPrompts）。
- `frontend/src/composables/useChatUrlParams.js` 已存在，返回 `{ userId, userName, orgNo, srcSysNo, channel }`。
- 向导前两页数据在 `frontend/src/stores/analysisStore.js`（模块级 reactive 单例）：`state.currentType`（'online'/'offline'）、`state.selectedActivityNames`（Set<string>）、`state.offlineStart/offlineEnd`、`state.canvasComps`（[{name,cat,desc,tpl}]）、`canGoNext`、`lockSummary`。

---

### Task 1: vitest 接入 + 抽取 `utils/agentTrace.js`

**Files:**
- Create: `frontend/src/utils/agentTrace.js`
- Create: `frontend/src/utils/agentTrace.test.js`
- Modify: `frontend/package.json`（devDependencies + test script）
- Modify: `frontend/src/views/UiChatView.vue`（删除已移出函数，改为 import）

**Interfaces:**
- Produces: `utils/agentTrace.js` 导出以下纯函数/常量（从 UiChatView.vue 原样搬运）：
  `TRACE_STEP_DISPLAY_NAMES`, `TRACE_STEP_ORDER`, `HIDDEN_TRACE_STEPS`, `DATA_PIPELINE_MERGE_GROUP`, `UPLOADED_FILE_PARSE_MERGE_GROUP`, `UPLOADED_DATA_PROCESSING_MERGE_GROUP`, `stepKey`, `traceDisplayName`, `traceStepOrder`, `isSingleActivityTrace`, `dataPipelineMergeGroup`, `buildMergedTraceStep`, `buildMergedDataPipelineStep`, `mergeDataPipelineSteps`, `isUploadedActivityTrace`, `mergeUploadedActivityTraceSteps`, `visibleTraceSteps`, `isTraceNode`, `stepStatusText`, `isPendingStep`, `upsertTraceStep`, `tracePayloadForStep`, `syncTracePlan`, `finishThinkingTrace`, `traceProgressText`, `shouldDisplayThinkingTrace`, `thinkingTitleText`, `activityTraceLabel`, `activityRouteSummary`, `templateMatchResult`, `templateMatchCandidates`, `activityTemplateMatchResult`, `templateListNames`, `showTemplateMatchDetail`, `showTemplateListDetail`。
  这些函数全部为纯函数（只操作入参，不引用组件作用域），搬运时不需要改动函数体。
- 后续 Task 4/5（useAgentChat）、Task 7（ChatMessageList）消费这些导出。

- [ ] **Step 1: 安装测试依赖并配置**

```bash
cd frontend && npm install -D vitest jsdom
```

在 `frontend/package.json` 的 scripts 中增加：

```json
"test": "vitest run"
```

- [ ] **Step 2: 编写失败测试**

创建 `frontend/src/utils/agentTrace.test.js`：

```js
import { describe, it, expect } from 'vitest';
import {
  visibleTraceSteps,
  traceProgressText,
  finishThinkingTrace,
  stepStatusText,
  traceDisplayName,
  upsertTraceStep,
  shouldDisplayThinkingTrace
} from './agentTrace.js';

function makeStep(node, status, extra = {}) {
  return { node, displayName: node, message: '', status, timestamp: 1, ...extra };
}

describe('agentTrace', () => {
  it('traceDisplayName 使用中文显示名', () => {
    expect(traceDisplayName('intent_recognition')).toBe('意图识别');
    expect(traceDisplayName('unknown_node', '', '兜底')).toBe('兜底');
  });

  it('stepStatusText 覆盖各状态', () => {
    expect(stepStatusText('done')).toBe('已完成');
    expect(stepStatusText('running')).toBe('执行中');
    expect(stepStatusText('failed')).toBe('执行失败');
    expect(stepStatusText('skipped')).toBe('已跳过');
    expect(stepStatusText('pending')).toBe('待执行');
  });

  it('visibleTraceSteps 将数据管线步骤合并为一个展示步骤', () => {
    const steps = [
      makeStep('intent_recognition', 'done'),
      makeStep('template_list_fetch', 'done'),
      makeStep('template_matching', 'running'),
      makeStep('component_value_fetch', 'pending'),
      makeStep('component_value_cleanup', 'pending'),
      makeStep('marketing_report_synthesis', 'pending')
    ];
    const visible = visibleTraceSteps({ steps });
    const merged = visible.find((s) => s.node === 'data_pipeline_merged');
    expect(merged).toBeTruthy();
    expect(merged.displayName).toBe('数据获取、处理与分析');
    expect(merged.status).toBe('running');
    // 合并后不再出现原子步骤
    expect(visible.some((s) => s.node === 'template_matching')).toBe(false);
  });

  it('visibleTraceSteps 隐藏 guard 步骤与 supervisor/finalize', () => {
    const steps = [
      makeStep('intent_recognition', 'done'),
      makeStep('report_html_guard', 'done'),
      makeStep('supervisor', 'done'),
      makeStep('finalize', 'done')
    ];
    const visible = visibleTraceSteps({ steps });
    expect(visible.map((s) => s.node)).toEqual(['intent_recognition']);
  });

  it('finishThinkingTrace 将 pending 步骤标记为 skipped', () => {
    const trace = {
      status: 'running',
      startedAt: Date.now() - 100,
      steps: [makeStep('intent_recognition', 'done'), makeStep('report_generation', 'pending')]
    };
    finishThinkingTrace(trace, {});
    expect(trace.status).toBe('done');
    expect(trace.steps[1].status).toBe('skipped');
    expect(trace.steps[1].skipReason).toBeTruthy();
  });

  it('finishThinkingTrace 等待审批时状态为 paused', () => {
    const trace = { status: 'running', startedAt: Date.now() - 100, steps: [] };
    finishThinkingTrace(trace, { awaiting_approval: true });
    expect(trace.status).toBe('paused');
  });

  it('traceProgressText 统计可见步骤进度', () => {
    const message = {
      status: 'running',
      steps: [makeStep('intent_recognition', 'done'), makeStep('marketing_data_fetch', 'running')]
    };
    expect(traceProgressText(message)).toBe('2/2');
  });

  it('upsertTraceStep 按 key 更新已有步骤并合并 payload', () => {
    const trace = { steps: [{ node: 'intent_recognition', status: 'running', payload: { a: 1 }, timestamp: 1 }] };
    upsertTraceStep(trace, { node: 'intent_recognition', status: 'done', payload: { b: 2 }, timestamp: 2 });
    expect(trace.steps).toHaveLength(1);
    expect(trace.steps[0].status).toBe('done');
    expect(trace.steps[0].payload).toEqual({ a: 1, b: 2 });
  });

  it('shouldDisplayThinkingTrace 空步骤不展示', () => {
    expect(shouldDisplayThinkingTrace({ status: 'done', steps: [] })).toBe(false);
    expect(shouldDisplayThinkingTrace({ status: 'running', steps: [makeStep('intent_recognition', 'running')] })).toBe(true);
  });
});
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/utils/agentTrace.test.js`
Expected: FAIL（`./agentTrace.js` 不存在）

- [ ] **Step 4: 原样搬运函数到 `utils/agentTrace.js`**

从 `frontend/src/views/UiChatView.vue` 将 **Interfaces 中列出的全部常量与函数**原样剪切到新文件 `frontend/src/utils/agentTrace.js`，逐个加 `export`。文件头加一行注释：

```js
// 思维链（execution_trace）展示相关的纯函数，从 UiChatView 抽取，供对话页与报告页共用。
```

注意点：
- `visibleTraceSteps` 依赖 `isUploadedActivityTrace`、`mergeUploadedActivityTraceSteps`、`mergeDataPipelineSteps`、`dataPipelineMergeGroup`、`traceStepOrder`、`isPendingStep`、`stepKey`、`traceDisplayName`、`HIDDEN_TRACE_STEPS`、`TRACE_STEP_ORDER` —— 都在本次搬运清单内，全部移完后文件自给自足，无需 import。
- `syncTracePlan`、`upsertTraceStep`、`finishThinkingTrace`、`tracePayloadForStep` 操作传入的 trace 对象，不涉及组件状态，原样搬运。
- 若发现清单内函数引用了未列入清单的组件作用域变量（理论上没有），停下来补齐清单再搬。

- [ ] **Step 5: UiChatView.vue 改为 import**

在 UiChatView.vue 顶部 import 区加入（只列实际仍被该文件引用的名字，先全量 import 再由构建告警逐项剔除也行，但最终保持精确）：

```js
import {
  visibleTraceSteps, traceProgressText, thinkingTitleText, shouldDisplayThinkingTrace,
  stepKey, traceDisplayName, isTraceNode, isPendingStep, stepStatusText,
  upsertTraceStep, syncTracePlan, finishThinkingTrace, tracePayloadForStep,
  showTemplateMatchDetail, showTemplateListDetail, templateMatchResult,
  templateMatchCandidates, activityTemplateMatchResult, templateListNames,
  activityTraceLabel, activityRouteSummary
} from '@/utils/agentTrace.js';
```

删除 UiChatView.vue 中已搬走的函数与常量定义。注意 `pruneEmptyCompletedTraces`、`finishRunningThinking`、`ensureThinkingTrace`、`resumePausedThinkingTrace`、`addRuntimeTrace`、`hasRunningThinking` **留在 UiChatView**（它们操作 conversation 状态，Task 4 才移入 composable）。

- [ ] **Step 6: 测试 + 构建验证**

```bash
cd frontend && npx vitest run && npm run build
```

Expected: 测试全部 PASS；build 成功无报错。

- [ ] **Step 7: 浏览器冒烟**

`npm run dev` 已在跑时直接打开 `http://localhost:3000/chat-ui`，发送一条消息，确认思考面板正常展开/折叠、步骤合并展示正常。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/utils/agentTrace.js frontend/src/utils/agentTrace.test.js frontend/package.json frontend/package-lock.json frontend/src/views/UiChatView.vue
git commit -m "抽取思维链展示纯函数到 utils/agentTrace"
```

---

### Task 2: 抽取 `utils/activityFormat.js`

**Files:**
- Create: `frontend/src/utils/activityFormat.js`
- Create: `frontend/src/utils/activityFormat.test.js`
- Modify: `frontend/src/views/UiChatView.vue`

**Interfaces:**
- Consumes: `frontend/src/utils/activityDictionaries.js` 的 `activityStatusTone`, `displayActivityStatus`, `displayActivityType`（activityTags 依赖，搬运时加 import）。
- Produces: `activityName`, `activityId`, `activityRowNumber`, `activityPeriod`, `activityTags`, `activitySummary`, `visibleActivities`, `compactActivity`, `compactTemplate`, `compactTracePayload`, `selectionActivities`, `allActivitySelectionChecked`, `selectedActivityRowNumbers`, `toggleActivitySelectionPure`。
- `toggleActivitySelectionPure(message, activity)`：现 `toggleActivitySelection` 去掉 `persistConversation()` 调用的纯版本（只改 `message.selectedIds`）。UiChatView 保留一个同名包装 `toggleActivitySelection` 调纯函数 + `persistConversation()`（Task 4 时包装移入 composable）。
- `setAllActivityRows` **不移**（依赖 activeConversation 与 DOM focus，Task 4 进 composable）。

- [ ] **Step 1: 编写失败测试**

创建 `frontend/src/utils/activityFormat.test.js`：

```js
import { describe, it, expect } from 'vitest';
import {
  activityName, activityId, activityRowNumber, activityPeriod,
  compactActivity, selectedActivityRowNumbers, toggleActivitySelectionPure,
  selectionActivities, allActivitySelectionChecked
} from './activityFormat.js';

describe('activityFormat', () => {
  it('activityName 兼容多种字段', () => {
    expect(activityName({ name: '薪运活动' })).toBe('薪运活动');
    expect(activityName({ actName: '代发活动' })).toBe('代发活动');
    expect(activityName({ '活动名称': '开门红' })).toBe('开门红');
    expect(activityName({})).toBe('未命名活动');
  });

  it('activityId 兼容多种字段', () => {
    expect(activityId({ activity_id: 'A001' })).toBe('A001');
    expect(activityId({ actNo: 'B002' })).toBe('B002');
    expect(activityId({ '活动编号': 'C003' })).toBe('C003');
  });

  it('activityRowNumber 非法值回退为索引+1', () => {
    expect(activityRowNumber({ row_number: 3 })).toBe(3);
    expect(activityRowNumber({}, 4)).toBe(5);
    expect(activityRowNumber({ row_number: 'x' }, 0)).toBe(1);
  });

  it('activityPeriod 拼接起止日期', () => {
    expect(activityPeriod({ start_date: '2024-01-01', end_date: '2024-03-31' })).toBe('2024-01-01 至 2024-03-31');
    expect(activityPeriod({})).toBe('');
  });

  it('compactActivity 提取核心字段', () => {
    const compact = compactActivity({ row_number: 2, activity_id: 'A1', name: '活动', channel: '短信', content: '内容' });
    expect(compact).toMatchObject({ row_number: 2, activity_id: 'A1', name: '活动', channel: '短信', content: '内容' });
  });

  it('toggleActivitySelectionPure 切换选中状态', () => {
    const message = { selectedIds: [] };
    const activity = { activity_id: 'A1' };
    toggleActivitySelectionPure(message, activity);
    expect(message.selectedIds).toEqual(['A1']);
    toggleActivitySelectionPure(message, activity);
    expect(message.selectedIds).toEqual([]);
  });

  it('selectedActivityRowNumbers 返回选中行号', () => {
    const message = {
      selectableActivities: [{ activity_id: 'A1', row_number: 1 }, { activity_id: 'A2', row_number: 2 }],
      selectedIds: ['A2']
    };
    expect(selectedActivityRowNumbers(message)).toEqual([2]);
  });

  it('allActivitySelectionChecked 判断全选', () => {
    const message = {
      selectableActivities: [{ activity_id: 'A1' }, { activity_id: 'A2' }],
      selectedIds: ['A1', 'A2']
    };
    expect(allActivitySelectionChecked(message)).toBe(true);
    expect(selectionActivities({ activities: [{ activity_id: 'A1' }] })).toHaveLength(1);
  });
});
```

Run: `cd frontend && npx vitest run src/utils/activityFormat.test.js`
Expected: FAIL（模块不存在）

- [ ] **Step 2: 原样搬运 + UiChatView 切换**

将 Interfaces 列出的函数从 UiChatView.vue 原样剪切到 `frontend/src/utils/activityFormat.js` 并加 `export`；文件顶部：

```js
// 活动对象字段兼容与选择相关的纯函数，从 UiChatView 抽取。
import { activityStatusTone, displayActivityStatus, displayActivityType } from './activityDictionaries.js';
```

`toggleActivitySelection` 拆分为：新文件导出 `toggleActivitySelectionPure`（不含 persist）；UiChatView 保留：

```js
function toggleActivitySelection(message, activity) {
  toggleActivitySelectionPure(message, activity);
  persistConversation();
}
```

UiChatView 顶部加 import（按实际引用调整名单）：

```js
import {
  activityName, activityId, activityRowNumber, activityPeriod, activityTags,
  activitySummary, visibleActivities, compactActivity, compactTemplate,
  compactTracePayload, selectionActivities, allActivitySelectionChecked,
  selectedActivityRowNumbers, toggleActivitySelectionPure
} from '@/utils/activityFormat.js';
```

- [ ] **Step 3: 测试 + 构建 + 冒烟**

```bash
cd frontend && npx vitest run && npm run build
```

浏览器打开 `/chat-ui` 发送消息触发活动列表，确认活动表格渲染、行选择、全选/全不选正常。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/utils/activityFormat.js frontend/src/utils/activityFormat.test.js frontend/src/views/UiChatView.vue
git commit -m "抽取活动字段兼容纯函数到 utils/activityFormat"
```

---

### Task 3: 抽取 `utils/htmlReport.js`

**Files:**
- Create: `frontend/src/utils/htmlReport.js`
- Create: `frontend/src/utils/htmlReport.test.js`
- Modify: `frontend/src/views/UiChatView.vue`

**Interfaces:**
- Consumes: `@/api/base.js` 的 `API_BASE`；`html2canvas`（动态 import，保持原样）。
- Produces（全部从 UiChatView 原样搬运，例外见下）：
  - 常量/桥：`IFRAME_RESIZE_SCRIPT`, `installPngSnapshotBridge`, `injectResizeScript`, `injectPngSnapshotBridge`
  - 文档处理：`buildHtmlDocument(message)`, `stripReportFooterNote(html)`, `escapeHtmlText`, `safeDownloadName`, `inlineEchartsScript`, `sanitizePngSnapshotHtml`, `waitForStaticFrame`, `waitForSnapshotAssets`, `pngRenderScale`
  - 导出：`openHtmlReportInNewTab(message)`, `downloadHtmlReport(message)`, `downloadPngReport(message, iframeEl)`（**签名调整**：原第二个参数是 event，内部 `event?.currentTarget?.closest('.html-report-card')?.querySelector('.html-report-preview')`；改为直接接收 iframe 元素。UiChatView 模板调用处同步改为传 iframe——Task 6 前临时在 UiChatView 保留一行包装：`const downloadPngReportFromEvent = (message, event) => downloadPngReport(message, event?.currentTarget?.closest('.html-report-card')?.querySelector('.html-report-preview'))`，模板改调 `downloadPngReportFromEvent`）
  - 导出遮罩共享状态（**新增**，替代 UiChatView 内的局部 ref）：
    ```js
    import { reactive } from 'vue';
    export const reportExportOverlay = reactive({ visible: false, label: '' });
    let exportOperationId = 0;
    export function beginReportExport(label) {
      exportOperationId += 1;
      reportExportOverlay.visible = true;
      reportExportOverlay.label = label;
      return exportOperationId;
    }
    export function finishReportExport(operationId) {
      if (operationId !== exportOperationId) return;
      reportExportOverlay.visible = false;
      reportExportOverlay.label = '';
    }
    ```
  - 全局监听安装（**新增**，把 UiChatView 的 `handleHtmlReportResize` / `handlePngSnapshotResult` 及 onMounted/onBeforeUnmount 里的注册/注销收拢）：
    ```js
    export function installHtmlReportBridges() {
      window.addEventListener('message', handleHtmlReportResize);
      window.addEventListener('message', handlePngSnapshotResult);
      return () => {
        window.removeEventListener('message', handleHtmlReportResize);
        window.removeEventListener('message', handlePngSnapshotResult);
      };
    }
    export function cancelPendingPngExports(reason = '页面已关闭，PNG 导出已取消') {
      for (const pending of pendingPngExports.values()) {
        window.clearTimeout(pending.timeoutId);
        pending.reject(new Error(reason));
      }
      pendingPngExports.clear();
    }
    ```
    （`handleHtmlReportResize`、`handlePngSnapshotResult`、`pendingPngExports`、`requestPngSnapshot`、`renderSnapshotToPng` 作为模块级内部实现随之搬运。）

- [ ] **Step 1: 编写失败测试**

创建 `frontend/src/utils/htmlReport.test.js`，文件首行指定 jsdom：

```js
// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import {
  stripReportFooterNote, safeDownloadName, pngRenderScale,
  escapeHtmlText, buildHtmlDocument
} from './htmlReport.js';

describe('htmlReport', () => {
  it('stripReportFooterNote 去除数据来源尾注', () => {
    const html = '<div><p>正文</p><p>数据来源：行内系统</p></div>';
    expect(stripReportFooterNote(html)).not.toContain('数据来源');
    expect(stripReportFooterNote(html)).toContain('正文');
  });

  it('safeDownloadName 清理非法字符并截断', () => {
    expect(safeDownloadName('a/b:c*d?"<>|')).toBe('a_b_c_d_');
    expect(safeDownloadName('')).toBe('活动分析报告');
    expect(safeDownloadName('x'.repeat(200)).length).toBeLessThanOrEqual(80);
  });

  it('pngRenderScale 正常尺寸返回 ≤2 的缩放', () => {
    expect(pngRenderScale(800, 1200)).toBe(2);
  });

  it('pngRenderScale 超大尺寸抛错', () => {
    expect(() => pngRenderScale(50000, 50000)).toThrow();
  });

  it('escapeHtmlText 转义特殊字符', () => {
    expect(escapeHtmlText('<b>"x"</b>')).toBe('&lt;b&gt;&quot;x&quot;&lt;/b&gt;');
  });

  it('buildHtmlDocument 注入 echarts 同步脚本与 resize 桥', () => {
    const out = buildHtmlDocument({ title: '测试', html: '<html><head></head><body><div id="chart-1"></div><script>{ "series": [] }</script></body></html>' });
    expect(out).toContain('/lib/echarts.min.js');
    expect(out).toContain('data-iframe-resize');
    // CDN 形式的 echarts 引用统一替换为本地路径
    const cdn = buildHtmlDocument({ title: 't', html: '<html><head><script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script></head><body></body></html>' });
    expect(cdn).not.toContain('cdn.jsdelivr.net');
  });
});
```

Run: `cd frontend && npx vitest run src/utils/htmlReport.test.js`
Expected: FAIL（模块不存在）

- [ ] **Step 2: 原样搬运 + UiChatView 切换**

按 Interfaces 搬运。UiChatView 删除：`IFRAME_RESIZE_SCRIPT`、`installPngSnapshotBridge`、`injectResizeScript`、`injectPngSnapshotBridge`、`handleHtmlReportResize`、`handlePngSnapshotResult`、`pendingPngExports`、`html2canvasLoader`、`beginReportExport`、`finishReportExport`、`buildHtmlDocument`、`downloadHtmlReport`、`safeDownloadName`、`requestPngSnapshot`、`sanitizePngSnapshotHtml`、`waitForStaticFrame`、`waitForSnapshotAssets`、`pngRenderScale`、`renderSnapshotToPng`、`downloadPngReport`、`escapeHtmlText`、`openHtmlReportInNewTab`、`inlineEchartsScript`，以及局部 `exportOverlay` ref 和 `exportOperationId`。

UiChatView 顶部 import：

```js
import {
  buildHtmlDocument, stripReportFooterNote, downloadHtmlReport, downloadPngReport,
  openHtmlReportInNewTab, installHtmlReportBridges, cancelPendingPngExports,
  reportExportOverlay
} from '@/utils/htmlReport.js';
```

UiChatView 其余调整：
- 模板中 `exportOverlay.visible` / `exportOverlay.label` 改为 `reportExportOverlay.visible` / `reportExportOverlay.label`；
- 模板 `downloadPngReport(message, $event)` 改为 `downloadPngReportFromEvent(message, $event)`（包装函数见 Interfaces）；
- onMounted 中两个 `window.addEventListener('message', ...)` 替换为 `uninstallReportBridges = installHtmlReportBridges()`（先声明 `let uninstallReportBridges = null`）；onBeforeUnmount 中对应 removeEventListener 与 pendingPngExports 清理替换为 `uninstallReportBridges?.(); cancelPendingPngExports();`。
- `restoreConversationReports` 里的 `stripReportFooterNote` 调用不变（已 import）。

- [ ] **Step 3: 测试 + 构建 + 冒烟**

```bash
cd frontend && npx vitest run && npm run build
```

浏览器走查 `/chat-ui`：生成/恢复一份 HTML 报告，确认卡片预览 iframe 自动撑高、下载 HTML、新页签全屏正常（PNG 下载若耗时较长可跳过，逻辑未改）。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/utils/htmlReport.js frontend/src/utils/htmlReport.test.js frontend/src/views/UiChatView.vue
git commit -m "抽取HTML报告渲染与导出到 utils/htmlReport"
```

---

### Task 4: 抽取 `composables/useAgentChat.js`（状态与持久化部分）

**Files:**
- Create: `frontend/src/composables/useAgentChat.js`
- Modify: `frontend/src/views/UiChatView.vue`

**Interfaces:**
- Consumes: Task 1/2 的 utils；`@/api/conversations.js`（createConversationAPI/renameConversationAPI/fetchConversationMessages/getUserId）；`@/api/agentRun.js`（resumeAgentV2）；`@/api/agentRunHistory.js`（submitReportFeedback/reportDownloadUrl）。
- Produces:

```js
export function useAgentChat(options = {})
// options:
//   getConversation: () => conversation | undefined   —— 所有 conversation 参数的缺省值
//   onScroll: (conversation) => void                  —— 替代原 scrollBottom
//   onConversationIdMigrated: (oldId, newId) => void  —— conv-* 本地会话注册迁移回调（Task 5 用）
//   urlParams: { userId, userName, orgNo, srcSysNo, channel }
// 返回（本任务部分）：
// {
//   // 工厂
//   createConversationState(init),          // => reactive 风格普通对象 { id, title, typing:false, dynamicMessages:[], ...init }
//   // 消息与持久化
//   addMessage(role, text, conversation?, metadata?),
//   persistConversation(conversation?),
//   restoreConversationMessages(conversation),   // => boolean
//   parseUserSelectionContent(content),
//   removeStaleTransportFallback(conversation?),
//   // 思维链状态
//   ensureThinkingTrace(conversation, startedAt),
//   resumePausedThinkingTrace(conversation?),
//   finishRunningThinking(conversation?, payload?),
//   hasRunningThinking(conversation?),
//   addRuntimeTrace(runtimeTrace, conversation?),
//   pruneEmptyCompletedTraces(conversation?),
//   // 报告消息
//   addHtmlReport(html, conversation?, payload?, insertIndex?),
//   isDownloadableExportMessage(message),
//   downloadExportArtifact(artifact),
//   restoreConversationReports(detail, conv),
//   loadConversation(conversation),          // 新增：封装 switchConversation 中的恢复分支（见下）
//   // 活动选择
//   toggleActivitySelection(message, activity),       // 纯切换 + persist
//   setAllActivityRows(message, checked),
//   attachActivitySelection(message, activities, conversation?),
//   removeComposerSelectedRow(rowNumber),
//   // 审批
//   addApprovalRequest(payload, conversation?),
//   formatApprovalArgs(args), formatApprovalDescription(message),
//   // 反馈
//   submitReportFeedbackToServer(message, feedback, comment?),
//   handleReportFeedback(message, feedback),
//   submitDislikeFeedback(message, skip?),
//   canSubmitReportFeedback(message),
//   // 计算属性
//   composerSelectionMessage, composerSelectedRows, hasPendingApproval,
//   // run 游标（Task 5 的流引擎也用，内部共享）
//   getRunSequence(conversationId), setRunSequence(conversationId, seq),
//   // 页面卸载标记（Task 5 用）
//   isPageUnloading: () => pageUnloading
// }
```

- `createConversationState`：
```js
function createConversationState(init = {}) {
  return {
    id: init.id || `conv-${Date.now()}`,
    title: init.title || '新建分析对话',
    meta: init.meta || '刚刚',
    group: init.group || 'today',
    typing: false,
    dynamicMessages: [...(init.messages || [])],
    ...init
  };
}
```

- `loadConversation`（新封装，行为等价于 UiChatView 现 switchConversation 中 `conv.dynamicMessages.length === 0` 分支）：
```js
async function loadConversation(conversation) {
  if (!conversation?.id) return;
  if (restoreConversationMessages(conversation)) {
    try {
      const detail = await fetchConversationMessages(conversation.id);
      conversation.agentVersion = detail.agentVersion || conversation.agentVersion || 'v2';
      addRuntimeTrace(detail.runtimeTrace, conversation);
      await restoreConversationReports(detail, conversation);
    } catch (e) {
      console.error('恢复报告内容失败', e);
    }
    return;
  }
  try {
    const detail = await fetchConversationMessages(conversation.id);
    const messages = Array.isArray(detail) ? detail : detail.messages || [];
    conversation.agentVersion = detail.agentVersion || conversation.agentVersion || 'v2';
    conversation.dynamicMessages = messages.map((m) => {
      if (m.role === 'user') {
        const parsed = parseUserSelectionContent(m.content);
        return { role: 'user', text: parsed.text, selectedRows: parsed.selectedRows };
      }
      return { role: 'ai', text: m.content };
    });
    addRuntimeTrace(detail.runtimeTrace, conversation);
    await restoreConversationReports(detail, conversation);
  } catch (e) {
    console.error('加载消息历史失败', e);
  }
}
```

- 页面卸载监听收进 composable（原 handlePageExit/handlePageShow + 三个 window 监听）：
```js
let pageUnloading = false;
function handlePageExit() { pageUnloading = true; }
function handlePageShow() { pageUnloading = false; }
// useAgentChat 内：
onMounted(() => {
  pageUnloading = false;
  window.addEventListener('beforeunload', handlePageExit);
  window.addEventListener('pagehide', handlePageExit);
  window.addEventListener('pageshow', handlePageShow);
});
onBeforeUnmount(() => {
  pageUnloading = true;
  window.removeEventListener('beforeunload', handlePageExit);
  window.removeEventListener('pagehide', handlePageExit);
  window.removeEventListener('pageshow', handlePageShow);
});
```

- [ ] **Step 1: 搬运实现**

创建 `frontend/src/composables/useAgentChat.js`：
- 文件顶部 import：`computed, nextTick, onMounted, onBeforeUnmount`（from 'vue'）、agentTrace utils、activityFormat utils、`stripReportFooterNote`（from utils/htmlReport.js）、`fetchConversationMessages, createConversationAPI, renameConversationAPI, getUserId`（conversations.js）、`resumeAgentV2`（agentRun.js）、`submitReportFeedback, reportDownloadUrl`（agentRunHistory.js）、`API_BASE`（base.js）。
- 从 UiChatView 原样搬运以下函数/常量，改为闭包内部函数：`SYSTEM_BUSY_MESSAGE`、`TRANSPORT_ERROR_MARKERS`、`isTransportError`、`requestErrorMessage`、`STORAGE_PREFIX`、`RUN_SEQUENCE_PREFIX`、`storageKey`、`runSequenceKey`、`getRunSequence`、`setRunSequence`、`compactMessageForStorage`、`persistConversation`、`restoreConversationMessages`、`parseUserSelectionContent`、`addMessage`、`downloadExportArtifact`、`isDownloadableExportMessage`、`addHtmlReport`、`hasRunningThinking`、`ensureThinkingTrace`、`resumePausedThinkingTrace`、`finishRunningThinking`、`addRuntimeTrace`、`pruneEmptyCompletedTraces`、`restoredReportPayload`、`findReportInsertIndex`、`restoreConversationReports`、`attachActivitySelection`、`addApprovalRequest`、`formatApprovalArgs`、`formatApprovalDescription`、`submitReportFeedbackToServer`、`handleReportFeedback`、`submitDislikeFeedback`、`canSubmitReportFeedback`、`removeStaleTransportFallback`。
- 搬运时把 `activeConversation.value` 替换为 `options.getConversation?.()`；把 `scrollBottom(x)` 替换为 `options.onScroll?.(x)`；把 `urlUserId/urlUserName/urlOrgNo/urlSrcSysNo/urlChannel` 替换为 `options.urlParams?.userId` 等。
- `toggleActivitySelection`（包装纯函数 + persist）、`setAllActivityRows`、`removeComposerSelectedRow` 一并移入（`setAllActivityRows` 内的 `activeConversation.value` 改为 `options.getConversation?.()`；其中的 `inputTextareaRef.value?.focus()` 删除——由 Task 7 的组件事件替代，此处只保留 `persistConversation()`）。
- 三个 computed（`composerSelectionMessage`、`composerSelectedRows`、`hasPendingApproval`）从 UiChatView 移入，内部 `activeConversation.value` 同样替换。
- UiChatView 改为：
  ```js
  const chat = useAgentChat({
    getConversation: () => activeConversation.value,
    onScroll: (conversation) => scrollBottom(conversation),
    onConversationIdMigrated: (oldId, newId) => {
      if (activeConversationId.value === oldId) activeConversationId.value = newId;
    },
    urlParams: {
      userId: urlUserId, userName: urlUserName, orgNo: urlOrgNo,
      srcSysNo: urlSrcSysNo, channel: urlChannel
    }
  });
  const {
    addMessage, persistConversation, restoreConversationMessages, loadConversation,
    addRuntimeTrace, finishRunningThinking, hasRunningThinking, pruneEmptyCompletedTraces,
    addHtmlReport, isDownloadableExportMessage, downloadExportArtifact,
    restoreConversationReports, toggleActivitySelection, setAllActivityRows,
    attachActivitySelection, removeComposerSelectedRow, addApprovalRequest,
    formatApprovalDescription, handleReportFeedback, submitDislikeFeedback,
    canSubmitReportFeedback, composerSelectionMessage, composerSelectedRows,
    hasPendingApproval, removeStaleTransportFallback, getRunSequence, setRunSequence
  } = chat;
  ```
  解构保持模板引用名不变，**模板零改动**。
- `switchConversation` 简化：`conv.dynamicMessages.length === 0` 分支替换为 `await loadConversation(conv)`（保留外围 editing/saveRename/activeConversationId 逻辑与 `recoverAgentRun` 调用——recoverAgentRun 本任务暂留 UiChatView）。
- UiChatView 的 `createConversation` 工厂替换为 `chat.createConversationState`（行为一致即可，保留原函数名作为包装）。
- UiChatView 删除已搬运的函数与常量、`pageUnloading` 及三个 window 监听（onMounted/onBeforeUnmount 中对应行）。

- [ ] **Step 2: 构建 + 全量测试 + 冒烟**

```bash
cd frontend && npx vitest run && npm run build
```

浏览器走查 `/chat-ui`：发消息、切换会话（触发 loadConversation）、刷新页面恢复对话与报告卡片、活动选择、点选行 chips。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/composables/useAgentChat.js frontend/src/views/UiChatView.vue
git commit -m "抽取会话状态与持久化到 useAgentChat composable"
```

---

### Task 5: `useAgentChat.js` 补完流式引擎（send/cancel/审批恢复/断线重连）

**Files:**
- Modify: `frontend/src/composables/useAgentChat.js`
- Modify: `frontend/src/views/UiChatView.vue`

**Interfaces:**
- Consumes: `@/api/agentRun.js` 的 `runAgentV2, cancelAgentV2, getAgentV2RunStatus, attachAgentV2Run`；Task 4 的全部内部函数。
- Produces（composable 返回值新增）：
  - `sendMessage({ text, uploadedFile, selectedRows, conversation? })` — 原 `sendMsg` 主体，签名变化：输入通过参数传入，不再读写 `inputText`/`uploadedFile` ref（清理由调用方组件负责）。内部保留：conv-\* 会话迁移（调 `options.onConversationIdMigrated`）、`displayText` 组装、`addMessage`、清空 `composerSelectionMessage.selectedIds`、首条消息标题同步（renameConversationAPI）、stale running trace 收尾、`runAgentV2` 调用、`consumeAgentStream`、异常兜底。
  - `cancelRun(conversation?)`
  - `resolveApproval(message, decision, editedArgs?)` — 原函数原样移入，`resumeAgentV2` 参数里的 urlParams 取自 options。
  - `consumeAgentStream(response, conversation, options?)`
  - `recoverAgentRun(conversation)`
  - `currentRunningTraceSnapshot`（computed，依赖 `visibleTraceSteps` 等，内部 activeConversation 替换为 getConversation）

- [ ] **Step 1: 搬运流式引擎**

从 UiChatView 原样移入 composable：`recoveringRunThreads`、`recoverAgentRun`、`reconnectAgentStream`、`consumeAgentStream`、`cancelRun`、`resolveApproval`、`currentRunningTraceSnapshot`。`sendMsg` 改造为上述 `sendMessage`：

```js
async function sendMessage({ text = '', uploadedFile = null, selectedRows = [], conversation = options.getConversation?.() } = {}) {
  const trimmedText = String(text || '').trim();
  const rows = [...(selectedRows || [])];
  if (!trimmedText && !uploadedFile?.file_path && rows.length === 0) return;
  if (!conversation || conversation.typing) return;

  const selectionText = rows.length ? `已选择第 ${rows.join('、')} 行` : '';
  const personalRequestText = trimmedText || (
    uploadedFile?.file_name ? `请基于上传的活动数据文件「${uploadedFile.file_name}」生成分析报告` : ''
  );
  const requestText = [selectionText, personalRequestText].filter(Boolean).join('\n');

  // 历史遗留的本地 conv-* 会话先注册到服务端并迁移 id
  if (conversation.id?.startsWith('conv-')) {
    try {
      const data = await createConversationAPI(conversation.title || '新建分析对话');
      const oldId = conversation.id;
      conversation.id = data.id;
      options.onConversationIdMigrated?.(oldId, data.id);
      const cached = localStorage.getItem(storageKey(oldId));
      if (cached) {
        localStorage.setItem(storageKey(data.id), cached);
        localStorage.removeItem(storageKey(oldId));
      }
    } catch (e) {
      console.warn('本地会话注册到服务端失败，继续使用本地会话', e);
    }
  }

  const displayText = uploadedFile?.file_name
    ? `${personalRequestText}\n\n附件：${uploadedFile.file_name}`
    : personalRequestText;
  addMessage('user', displayText, conversation, { selectedRows: rows });
  if (composerSelectionMessage.value) {
    composerSelectionMessage.value.selectedIds = [];
    persistConversation(conversation);
  }

  const isFirstUserMessage = conversation.dynamicMessages.filter((m) => m.role === 'user').length === 1;
  if (isFirstUserMessage && conversation.title) {
    try {
      await renameConversationAPI(conversation.id, conversation.title);
    } catch (e) {
      console.error('同步标题失败', e);
    }
  }

  conversation.typing = true;
  setRunSequence(conversation.id, 0);
  options.onScroll?.(conversation);

  const staleRunningTrace = conversation.dynamicMessages.find((message) => (
    message.role === 'execution_trace' && message.status === 'running'
  ));
  if (staleRunningTrace) {
    finishThinkingTrace(staleRunningTrace, { message: '前一次任务已中断' });
  }

  try {
    const response = await runAgentV2({
      threadId: conversation.id,
      message: requestText,
      originalUserText: displayText || requestText,
      filePath: uploadedFile?.file_path || '',
      userId: options.urlParams?.userId || getUserId(),
      userName: options.urlParams?.userName,
      orgNo: options.urlParams?.orgNo,
      srcSysNo: options.urlParams?.srcSysNo,
      channel: options.urlParams?.channel
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `请求失败：${response.status}`);
    }
    await consumeAgentStream(response, conversation);
  } catch (e) {
    conversation.typing = false;
    finishRunningThinking(conversation);
    addMessage('ai', requestErrorMessage(e), conversation);
  }
}
```

- [ ] **Step 2: UiChatView 切换**

- 删除 `sendMsg`、`cancelRun`、`resolveApproval`、`consumeAgentStream`、`reconnectAgentStream`、`recoverAgentRun`、`recoveringRunThreads`、`currentRunningTraceSnapshot` 及不再需要的 import。
- 从 chat 解构补充：`sendMessage: chatSendMessage, cancelRun, resolveApproval, consumeAgentStream, recoverAgentRun, currentRunningTraceSnapshot`。
- 保留本地薄包装（模板与输入逻辑仍需要本地 inputText/uploadedFile 清理，Task 8 前过渡）：

```js
async function sendMsg() {
  const text = inputText.value.trim();
  const currentUploadedFile = uploadedFile.value;
  const selectedRows = [...composerSelectedRows.value];
  if (!text && !currentUploadedFile?.file_path && selectedRows.length === 0) return;
  if (activeConversation.value?.typing) return;
  inputText.value = '';
  uploadedFile.value = null;
  uploadError.value = '';
  await chatSendMessage({ text, uploadedFile: currentUploadedFile, selectedRows });
}
```

（原 sendMsg 中的 conv-\* 迁移、标题同步等已进 composable，包装里不再重复。）
- `switchConversation` 中 `await recoverAgentRun(conv)` 不变（已解构）。

- [ ] **Step 3: 构建 + 测试 + 冒烟**

```bash
cd frontend && npx vitest run && npm run build
```

浏览器走查 `/chat-ui` 完整链路：发消息→思考面板流式更新→生成报告→追问→（如有）审批确认/拒绝→停止按钮→刷新恢复进行中任务。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/composables/useAgentChat.js frontend/src/views/UiChatView.vue
git commit -m "抽取流式对话引擎到 useAgentChat"
```

---

### Task 6: 抽取 `components/chat/HtmlReportCard.vue`

**Files:**
- Create: `frontend/src/components/chat/HtmlReportCard.vue`
- Modify: `frontend/src/views/UiChatView.vue`

**Interfaces:**
- Consumes: `utils/htmlReport.js`（buildHtmlDocument/downloadHtmlReport/downloadPngReport/openHtmlReportInNewTab/reportExportOverlay）；useAgentChat 返回的反馈函数。
- Produces:

```
<HtmlReportCard :message="message" :chat="chat" mode="card|slim|stage" @locate="..." />
```

- `message`：html_report 消息对象（`{ title, html, requestId, reportRequestId, versionNo, reportContext, feedback, feedbackComment, feedbackSaving, feedbackError, commentEditorOpen, feedbackCommentDraft, showHistory }`）。
- `chat`：useAgentChat 返回值（用 `chat.handleReportFeedback`、`chat.submitDislikeFeedback`、`chat.canSubmitReportFeedback`）。
- `mode`：`'card'`（默认，chat-ui 现有完整卡片）；`'slim'`（轻量条：图标 + "报告已生成/已更新至 vN" + "查看报告"按钮，点击 emit `locate`）；`'stage'`（报告页主报告区：同 card 但去掉头像行适配、iframe 最小高度更大）。
- UiChatView 模板中 `message.role === 'html_report'` 的整个分支替换为：

```html
<div v-else-if="message.role === 'html_report'" class="msg-row">
  <div class="avatar av-ai"><i class="ti ti-file-analytics" aria-hidden="true"></i></div>
  <HtmlReportCard :message="message" :chat="chat" />
</div>
```

（头像留在调用方，卡片根节点保持 `.html-report-card`。）

- [ ] **Step 1: 创建组件**

把 UiChatView 模板中 `.html-report-card` 整块（含版本条、历史、反馈、iframe）搬入新组件；`downloadPngReport(message, $event)` 调用改为组件内通过 ref 拿 iframe：

```html
<iframe ref="iframeRef" class="html-report-preview" :srcdoc="reportDocument" title="HTML报告预览" sandbox="allow-scripts"></iframe>
```

```js
const iframeRef = ref(null);
const reportDocument = computed(() => buildHtmlDocument(props.message));
function onDownloadPng() {
  downloadPngReport(props.message, iframeRef.value);
}
```

反馈相关模板绑定改为 `props.chat.handleReportFeedback(...)` 等（或解构）。slim 模式模板：

```html
<div v-if="mode === 'slim'" class="html-report-card slim">
  <div class="html-report-slim-row">
    <i class="ti ti-file-analytics" aria-hidden="true"></i>
    <span>报告已{{ (message.versionNo || 1) > 1 ? `更新至 v${message.versionNo}` : '生成' }}，已在上方报告区展示</span>
    <button type="button" class="html-download-btn secondary" @click="$emit('locate')">查看报告</button>
  </div>
</div>
```

CSS：从 UiChatView 的 `<style scoped>` 中把 `.html-report-*`、`.report-feedback-*`、`.version-*`、`.history-*` 相关选择器移入组件 scoped style；`.slim` 相关新增样式自补（单行、与卡片同边框风格）。

- [ ] **Step 2: UiChatView 切换 + 验证**

import 组件并注册；删除已移走的模板块与 CSS。`npm run build` + 浏览器确认报告卡片外观/按钮/反馈与改动前一致。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/chat/HtmlReportCard.vue frontend/src/views/UiChatView.vue
git commit -m "抽取HTML报告卡片组件"
```

---

### Task 7: 抽取 `components/chat/ChatMessageList.vue`

**Files:**
- Create: `frontend/src/components/chat/ChatMessageList.vue`
- Modify: `frontend/src/views/UiChatView.vue`

**Interfaces:**
- Consumes: Task 1/2 utils、Task 6 HtmlReportCard、现有 `ThinkingStatusIcon.vue`、`TraceTemplateMatch.vue`、`@/utils/markdown.js` 的 `renderMarkdown`、`activityDictionaries.js` 的 `replaceActivityStatusCodes/displayActivityStatus`。
- Produces:

```
<ChatMessageList
  :chat="chat"
  :conversation="activeConversation"
  report-card-mode="full|slim"
  @focus-composer="..."
  @locate-report="..."
>
  <template #greeting>...（可选，开场白气泡）</template>
</ChatMessageList>
```

- 渲染内容（从 UiChatView 的 `v-for="(message, index) in dynamicMessages"` 整块搬运）："新对话开始" divider、greeting 插槽、user/ai 气泡（markdown + 已选行 chips + 导出按钮 + 全选/全不选）、system 消息、approval_request 审批卡、html_report（用 HtmlReportCard，`mode="slim"` 当 `reportCardMode === 'slim'`，`@locate="$emit('locate-report')"`）、execution_trace 思考面板（含全部详情子块）、typing 动画（`conversation.typing && !chat.hasRunningThinking(conversation)`）。
- `renderMessageMarkdown` / `handleMarkdownActivityTableClick` 一并搬入（它们只用 message 与 selection helpers；`handleMarkdownActivityTableClick` 里清空其他表格选择的循环用 `props.conversation.dynamicMessages`，末尾的 `inputTextareaRef` focus 改为 `emit('focus-composer')`）。
- `setAllActivityRows`/`removeComposerSelectedRow` 调用 chat 上的方法；选择后的 focus 同样改 emit。

- [ ] **Step 1: 创建组件并搬运模板与 CSS**

script setup：

```js
import HtmlReportCard from './HtmlReportCard.vue';
import ThinkingStatusIcon from '../common/ThinkingStatusIcon.vue';
import TraceTemplateMatch from './TraceTemplateMatch.vue';
import { renderMarkdown } from '@/utils/markdown.js';
import { displayActivityStatus, replaceActivityStatusCodes } from '@/utils/activityDictionaries.js';
import {
  visibleTraceSteps, traceProgressText, thinkingTitleText, shouldDisplayThinkingTrace,
  stepKey, isTraceNode, isPendingStep, showTemplateMatchDetail, showTemplateListDetail,
  templateMatchResult, templateMatchCandidates, activityTemplateMatchResult,
  templateListNames, activityTraceLabel, activityRouteSummary
} from '@/utils/agentTrace.js';
import {
  activityName, activityId, activityRowNumber, activityPeriod, activityTags,
  activitySummary, visibleActivities, selectionActivities,
  allActivitySelectionChecked, selectedActivityRowNumbers
} from '@/utils/activityFormat.js';

const props = defineProps({
  chat: { type: Object, required: true },
  conversation: { type: Object, required: true },
  reportCardMode: { type: String, default: 'full' }
});
const emit = defineEmits(['focus-composer', 'locate-report']);

const dynamicMessages = computed(() => props.conversation?.dynamicMessages || []);

function renderMessageMarkdown(message) {
  return renderMarkdown(message?.text || '', {
    selectedRowNumbers: selectedActivityRowNumbers(message),
    transformText: replaceActivityStatusCodes,
    transformTableCell(cell, { headers, columnIndex }) {
      const normalizedHeaders = headers.map((header) => header.replace(/<[^>]+>|[*_`]/g, '').trim());
      const isActivityTable = normalizedHeaders.some((header) => ['活动名称', '活动编号', '活动ID'].includes(header));
      const isStatusColumn = ['状态', '活动状态'].includes(normalizedHeaders[columnIndex]);
      return isActivityTable && isStatusColumn ? displayActivityStatus(cell) : cell;
    }
  });
}

function handleMarkdownActivityTableClick(event, message) {
  if (!selectionActivities(message).length) return;
  const row = event.target?.closest?.('tbody tr[data-row-number]');
  if (!row || !event.currentTarget?.contains(row)) return;
  const rowNumber = Number(row.dataset.rowNumber);
  const activities = selectionActivities(message);
  const activity = activities.find((item, index) => activityRowNumber(item, index) === rowNumber);
  if (!activity) return;
  for (const item of props.conversation?.dynamicMessages || []) {
    if (item !== message && item.role === 'ai' && Array.isArray(item.selectableActivities)) {
      item.selectedIds = [];
    }
  }
  props.chat.toggleActivitySelection(message, activity);
  emit('focus-composer');
}
```

CSS：从 UiChatView 移入 `.msg-row`、`.avatar`、`.bubble`、`.md-body`、`.typing-dot`、`.system-*`、`.trace-*`、`.activity-*`、`.detail-*`、`.capability-*`、`.selected-row-circle`、`.user-selected-row-chips`、`.inline-table-bulk-actions`、`.export-artifact-btn`、`.divider-msg` 等相关选择器。

- [ ] **Step 2: UiChatView 切换**

消息 v-for 整块替换为：

```html
<ChatMessageList
  :chat="chat"
  :conversation="activeConversation"
  @focus-composer="inputTextareaRef?.focus()"
>
  <template #greeting>
    <div class="msg-row">
      <div class="avatar av-ai"><i class="ti ti-sparkles" aria-hidden="true"></i></div>
      <div class="bubble">
        <p>您好！我是活动分析助手。</p>
        <p>请告诉我您想分析的活动类型或具体问题，我会自动匹配相关活动并生成专业分析报告。</p>
      </div>
    </div>
  </template>
</ChatMessageList>
```

（typing 动画随之移入组件，UiChatView 删除对应块；`scrollToRunningTrace` 保留在 UiChatView——它操作 chatBody DOM。）

- [ ] **Step 3: 验证 + Commit**

`npm run build`；浏览器走查 `/chat-ui`：气泡、markdown 表格、行选择、思考面板展开/详情、审批卡、typing 动画。

```bash
git add frontend/src/components/chat/ChatMessageList.vue frontend/src/views/UiChatView.vue
git commit -m "抽取消息列表组件 ChatMessageList"
```

---

### Task 8: 抽取 `components/chat/ChatComposer.vue`

**Files:**
- Create: `frontend/src/components/chat/ChatComposer.vue`
- Modify: `frontend/src/views/UiChatView.vue`

**Interfaces:**
- Consumes: `@/api/files.js` uploadFile、`@/api/quickPrompts.js` fetchQuickPrompts、`ThinkingStatusIcon.vue`。
- Produces:

```
<ChatComposer :chat="chat" :conversation="activeConversation" @locate-trace="..." />
```

- 自有状态（从 UiChatView 搬入）：`inputText`、`inputTextareaRef`、`inputTextareaHeight` 及拖拽调整高度逻辑、`uploadedFile/uploadingFile/uploadError`、`draggingFile/dragDepth`、`fileInputRef`、`quickPrompts`（含 `DEFAULT_QUICK_QUESTION_PROMPTS` 与 onMounted 拉取远端话术）、`ACCEPTED_UPLOAD_EXTENSIONS`、输入框 resize 常量与 pointer 逻辑。
- 发送：

```js
async function sendMsg() {
  const text = inputText.value.trim();
  const currentUploadedFile = uploadedFile.value;
  const selectedRows = [...props.chat.composerSelectedRows.value];
  if (!text && !currentUploadedFile?.file_path && selectedRows.length === 0) return;
  if (props.conversation?.typing) return;
  inputText.value = '';
  uploadedFile.value = null;
  uploadError.value = '';
  await props.chat.sendMessage({ text, uploadedFile: currentUploadedFile, selectedRows });
}
```

- `canSend` computed 搬入（依赖 `props.chat.hasPendingApproval`、`inputText`、`uploadedFile`、`props.chat.composerSelectedRows`）。
- 文件上传/拖拽系列函数（triggerFileUpload/canUploadNow/isDragWithFiles/validateUploadFile/uploadSelectedFile/handleFileSelected/handleFileDragEnter/handleFileDragOver/handleFileDragLeave/handleFileDrop/removeUploadedFile）、`handleKey`、`useQuickQuestionPrompt`、输入框 resize 系列（startInputResize/handleInputResizeMove/stopInputResize/clampInputTextareaHeight）全部搬入。
- 模板：footer `.chat-input-area` 整块搬入（浮动进度条 `chat.currentRunningTraceSnapshot` 点击改 `emit('locate-trace')`、快捷提问 chips、deep-input-container、上传状态行、工具栏、发送/停止按钮）。`activeConversation.typing` → `props.conversation?.typing`；`scrollToRunningTrace` → emit。
- defineExpose({ focus: () => inputTextareaRef.value?.focus() })，供父级 focus-composer 时调用。

- [ ] **Step 1: 创建组件并搬运**

按 Interfaces 搬运模板 + 逻辑 + CSS（`.chat-input-area`、`.floating-task-progress*`、`.quick-prompt-*`、`.deep-input-container`、`.input-*`（保留 UiChatView 仍用的除外）、`.deep-textarea`、`.tool-*`、`.send-btn-circle`、`.upload-*`、`.drag-upload-mask`、`.composer-selected-*`、`.hidden-file-input`、`.spinning`）。

- [ ] **Step 2: UiChatView 切换**

footer 整块替换为：

```html
<footer class="chat-input-area-host">
  <ChatComposer
    ref="composerRef"
    :chat="chat"
    :conversation="activeConversation"
    @locate-trace="scrollToRunningTrace"
  />
</footer>
```

注意：原 footer 标签本身是组件模板根的一部分，直接把 `<footer class="chat-input-area">` 连同内容移入组件，UiChatView 只留 `<ChatComposer>` 调用。`@focus-composer`（Task 7 的消息列表事件）改为 `composerRef.value?.focus()`。UiChatView 删除已搬走的状态/函数/onMounted 中 fetchQuickPrompts 逻辑/onBeforeUnmount 中 stopInputResize。

- [ ] **Step 3: 验证 + Commit**

`npm run build`；浏览器走查 `/chat-ui`：输入发送、Enter/Shift+Enter、快捷提问、上传附件、拖拽上传、停止按钮、浮动进度点击定位、输入框拖拽调高。功能应与抽取前完全一致。

```bash
git add frontend/src/components/chat/ChatComposer.vue frontend/src/views/UiChatView.vue
git commit -m "抽取对话输入区组件 ChatComposer"
```

---

### Task 9: analysisStore 支持真实线下文件 + compose 页重置报告会话

**Files:**
- Modify: `frontend/src/stores/analysisStore.js`
- Modify: `frontend/src/components/source/OfflineSourceConfig.vue`
- Modify: `frontend/src/views/SkillComposerView.vue`

**Interfaces:**
- Consumes: `@/api/files.js` uploadFile。
- Produces:
  - analysisStore：`state.offlineFile`（`null | { file_name, file_path, size }`）替代 `state.uploadDone`；`setOfflineFile(fileInfo)`、`clearOfflineFile()`、`resetReportSession()`（`localStorage.removeItem('report_page_session')`）。`canGoNext` 线下分支改为 `Boolean(state.offlineFile?.file_path && state.offlineStart && state.offlineEnd && state.offlineStart <= state.offlineEnd)`；`setAnalysisType(type, true)` 重置时 `state.offlineFile = null`；`lockSummary.source` 线下分支改为 `state.offlineFile?.file_name || '线下活动数据'`。
  - ReportView（Task 10）消费：`state.offlineFile`、`resetReportSession`、常量 `REPORT_SESSION_KEY = 'report_page_session'`（从 analysisStore 导出，ReportView 与 SkillComposerView 共用）。

- [ ] **Step 1: 改造 analysisStore**

- `state.uploadDone` 替换为 `state.offlineFile = null`；删除 `toggleUpload`，新增（`setOfflineFile`/`clearOfflineFile`/`resetReportSession` 定义在 `useAnalysisStore` 内并加入 return；`REPORT_SESSION_KEY` 为**模块级命名导出**，供 ReportView/SkillComposerView import）：

```js
// 模块级：
export const REPORT_SESSION_KEY = 'report_page_session';

// useAnalysisStore 内：
function setOfflineFile(fileInfo) {
  state.offlineFile = fileInfo ? {
    file_name: fileInfo.file_name || '',
    file_path: fileInfo.file_path || '',
    size: fileInfo.size || 0
  } : null;
}

function clearOfflineFile() {
  state.offlineFile = null;
}

function resetReportSession() {
  try {
    localStorage.removeItem(REPORT_SESSION_KEY);
  } catch (e) {
    console.warn('清除报告会话失败', e);
  }
}
```

- `canGoNext`、`lockSummary`、`setAnalysisType` 按 Interfaces 调整；return 对象中 `toggleUpload` 替换为 `setOfflineFile, clearOfflineFile, resetReportSession`，并导出 `REPORT_SESSION_KEY`。

- [ ] **Step 2: OfflineSourceConfig 接真实上传**

完整替换 `<script setup>`：

```js
import { computed, ref } from 'vue';
import { uploadFile } from '../../api/files';
import { useAnalysisStore } from '../../stores/analysisStore';

const ACCEPTED_EXTENSIONS = ['.csv', '.xls', '.xlsx', '.xlsm', '.xltx', '.xltm'];

const store = useAnalysisStore();
const fileInputRef = ref(null);
const uploading = ref(false);
const uploadError = ref('');

const uploadText = computed(() => {
  if (uploading.value) return '正在上传...';
  if (store.state.offlineFile) return `${store.state.offlineFile.file_name} - 上传成功`;
  return '点击选择文件上传';
});

const uploadSub = computed(() => {
  if (uploadError.value) return uploadError.value;
  if (store.state.offlineFile) return '点击重新选择';
  return `支持 ${ACCEPTED_EXTENSIONS.join(' / ')} 文件`;
});

function updateStart(value) {
  store.setOfflineDates(value, store.state.offlineEnd);
}

function updateEnd(value) {
  store.setOfflineDates(store.state.offlineStart, value);
}

function triggerSelect() {
  if (uploading.value) return;
  uploadError.value = '';
  fileInputRef.value?.click();
}

async function handleFileChange(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  const lowerName = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext))) {
    uploadError.value = `仅支持 ${ACCEPTED_EXTENSIONS.join('、')} 文件`;
    return;
  }
  uploading.value = true;
  uploadError.value = '';
  try {
    const result = await uploadFile(file);
    store.setOfflineFile({ file_name: result.file_name || file.name, file_path: result.file_path, size: file.size });
  } catch (e) {
    store.clearOfflineFile();
    uploadError.value = e.message || '文件上传失败';
  } finally {
    uploading.value = false;
  }
}
</script>
```

模板：上传按钮改为真实文件选择——

```html
<input
  ref="fileInputRef"
  type="file"
  style="display: none"
  :accept="ACCEPTED_EXTENSIONS.join(',')"
  @change="handleFileChange"
/>
<button class="uz" :class="{ ok: store.state.offlineFile }" type="button" :disabled="uploading" @click="triggerSelect">
  <i :class="store.state.offlineFile ? 'ti ti-circle-check' : (uploading ? 'ti ti-loader-2' : 'ti ti-cloud-upload')"></i>
  <p>{{ uploadText }}</p>
  <small :style="uploadError ? 'color: var(--danger, #F53F3F)' : ''">{{ uploadSub }}</small>
</button>
```

同时把说明文案 `支持 .xlsx / .pdf / .docx，单文件 ≤ 20MB` 与 itip 中的 `（Excel/PDF/Word）` 修正为实际支持的表格格式。

- [ ] **Step 3: SkillComposerView 生成按钮重置会话**

`SkillComposerView.vue` 底部"生成分析报告"按钮（当前 `@click="router.push({ name: 'report' })"`）改为调用方法：

```js
function goReport() {
  store.resetReportSession();
  router.push({ name: 'report' });
}
```

模板改为 `@click="goReport"`。

- [ ] **Step 4: 验证 + Commit**

`npm run build`；浏览器走查 `/main` → 线下活动：选择文件真实上传成功、日期校验、下一步可点；线上路径不受影响。

```bash
git add frontend/src/stores/analysisStore.js frontend/src/components/source/OfflineSourceConfig.vue frontend/src/views/SkillComposerView.vue
git commit -m "线下活动接入真实文件上传"
```

---

### Task 10: 重写 ReportView 接入真实智能体

**Files:**
- Modify: `frontend/src/views/ReportView.vue`（整体重写）
- Delete: `frontend/src/components/common/ChatPanel.vue`、`frontend/src/components/report/ReportSummary.vue`、`frontend/src/components/report/BarChartList.vue`（仅被 ReportView 引用的 mock 组件）

**Interfaces:**
- Consumes: Task 4/5 `useAgentChat`、Task 6 `HtmlReportCard`、Task 7 `ChatMessageList`、Task 8 `ChatComposer`、Task 9 `REPORT_SESSION_KEY` 与 store；`useChatUrlParams`；`createConversationAPI/fetchConversationMessages`；`utils/htmlReport.js` 的 `downloadHtmlReport, installHtmlReportBridges, cancelPendingPngExports, reportExportOverlay`。
- Produces: 无（终端页面）。

- [ ] **Step 1: 整体重写 ReportView.vue**

```vue
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import TopBar from '../components/layout/TopBar.vue';
import ChatMessageList from '../components/chat/ChatMessageList.vue';
import ChatComposer from '../components/chat/ChatComposer.vue';
import HtmlReportCard from '../components/chat/HtmlReportCard.vue';
import { useAnalysisStore, REPORT_SESSION_KEY } from '../stores/analysisStore';
import { useAgentChat } from '../composables/useAgentChat';
import { useChatUrlParams } from '../composables/useChatUrlParams';
import { createConversationAPI, fetchConversationMessages } from '@/api/conversations.js';
import {
  downloadHtmlReport, installHtmlReportBridges, cancelPendingPngExports,
  reportExportOverlay
} from '@/utils/htmlReport.js';

const router = useRouter();
const store = useAnalysisStore();
const urlParams = useChatUrlParams();

const chatBody = ref(null);
const composerRef = ref(null);
const conversation = ref(null);
const booting = ref(false);
const bootError = ref('');
// 无会话快照且前两步无有效选择 → 空态
const emptyState = ref(false);

function scrollBottom() {
  nextTick(() => {
    window.setTimeout(() => {
      if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight;
    }, 50);
  });
}

const chat = useAgentChat({
  getConversation: () => conversation.value,
  onScroll: () => scrollBottom(),
  urlParams
});

// 最新报告消息（addHtmlReport 原地更新同 requestId，新报告追加，末位即当前报告）
const latestReport = computed(() => {
  const messages = conversation.value?.dynamicMessages || [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i]?.role === 'html_report' && messages[i].html) return messages[i];
  }
  return null;
});

const generating = computed(() => Boolean(conversation.value?.typing));

// 信息头数据：优先会话快照（刷新恢复），否则取 store
const sessionContext = ref(null);
const headerInfo = computed(() => {
  const ctx = sessionContext.value;
  if (ctx) return ctx;
  const isOnline = store.state.currentType === 'online';
  return {
    type: store.state.currentType,
    typeName: isOnline ? '线上活动' : '线下活动',
    activityNames: isOnline ? [...store.state.selectedActivityNames] : [],
    period: store.lockSummary.value.period,
    compNames: store.state.canvasComps.map((c) => c.name),
    fileName: store.state.offlineFile?.file_name || ''
  };
});

const reportTitle = computed(() => latestReport.value?.title || '活动分析报告');

function snapshotFromStore() {
  const isOnline = store.state.currentType === 'online';
  return {
    type: store.state.currentType,
    typeName: isOnline ? '线上活动' : '线下活动',
    activityNames: isOnline ? [...store.state.selectedActivityNames] : [],
    period: store.lockSummary.value.period,
    compNames: store.state.canvasComps.map((c) => c.name),
    fileName: store.state.offlineFile?.file_name || '',
    filePath: store.state.offlineFile?.file_path || '',
    offlineStart: store.state.offlineStart,
    offlineEnd: store.state.offlineEnd
  };
}

function buildInitialMessage(ctx) {
  const compPart = ctx.compNames?.length
    ? `分析框架请包含以下组件：${ctx.compNames.join('、')}。`
    : '';
  if (ctx.type === 'offline') {
    const period = ctx.offlineStart && ctx.offlineEnd ? `（统计周期 ${ctx.offlineStart} 至 ${ctx.offlineEnd}）` : '';
    return {
      text: `请基于上传的活动数据文件「${ctx.fileName}」${period}生成分析报告。${compPart}`,
      filePath: ctx.filePath || ''
    };
  }
  const names = (ctx.activityNames || []).map((n) => `「${n}」`).join('');
  return { text: `请为以下线上活动生成分析报告：${names}。${compPart}`, filePath: '' };
}

function readSession() {
  try {
    const raw = localStorage.getItem(REPORT_SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function writeSession(conversationId, context) {
  try {
    localStorage.setItem(REPORT_SESSION_KEY, JSON.stringify({
      conversationId,
      context,
      createdAt: new Date().toISOString()
    }));
  } catch (e) {
    console.warn('保存报告会话失败', e);
  }
}

// 刷新/恢复路径：根据快照重建会话并拉取历史
async function restoreSession(session) {
  sessionContext.value = session.context || null;
  const conv = chat.createConversationState({ id: session.conversationId, title: '活动分析报告' });
  conversation.value = conv;
  await chat.loadConversation(conv);
  scrollBottom();
  await chat.recoverAgentRun(conv);
}

// 正常路径：新建会话，组装首条消息自动开始生成
async function startNewReport() {
  const ctx = snapshotFromStore();
  sessionContext.value = ctx;
  const data = await createConversationAPI('新建分析对话');
  const conv = chat.createConversationState({ id: data.id, title: data.title || '新建分析对话' });
  conversation.value = conv;
  writeSession(conv.id, ctx);
  const initial = buildInitialMessage(ctx);
  await chat.sendMessage({
    text: initial.text,
    uploadedFile: initial.filePath ? { file_name: ctx.fileName, file_path: initial.filePath } : null,
    selectedRows: []
  });
}

async function bootstrap() {
  const session = readSession();
  booting.value = true;
  bootError.value = '';
  emptyState.value = false;
  try {
    if (session?.conversationId) {
      await restoreSession(session);
      return;
    }
    if (!store.canGoNext.value) {
      emptyState.value = true;
      return;
    }
    await startNewReport();
  } catch (e) {
    console.error('初始化报告页失败', e);
    bootError.value = e?.message || '初始化失败';
  } finally {
    booting.value = false;
  }
}

let uninstallBridges = null;
onMounted(() => {
  uninstallBridges = installHtmlReportBridges();
  bootstrap();
});

onBeforeUnmount(() => {
  uninstallBridges?.();
  cancelPendingPngExports();
});

function scrollToReport() {
  nextTick(() => {
    document.querySelector('.report-stage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function scrollToRunningTrace() {
  const conv = conversation.value;
  const trace = conv?.dynamicMessages?.find((m) => m.role === 'execution_trace' && m.status === 'running');
  if (!trace || !chatBody.value) return;
  const index = conv.dynamicMessages.indexOf(trace);
  nextTick(() => {
    const target = chatBody.value.querySelector(`[data-trace-index="${index}"]`);
    if (target) chatBody.value.scrollTo({ top: target.offsetTop - 80, behavior: 'smooth' });
  });
}

function exportReport() {
  if (latestReport.value) downloadHtmlReport(latestReport.value);
}

function retryBoot() {
  store.resetReportSession();
  bootstrap();
}
</script>
```

实现注意：空态模板中加入重试入口——当 `bootError` 非空且非空态时，在报告区占位下方显示"重试"按钮调用 `retryBoot`（清空会话快照后重新走 `bootstrap` 新建会话）。
- 模板结构：

```html
<template>
  <div class="page">
    <TopBar current-label="分析报告" :step="3" />

    <!-- 空态：未经前两步直接进入 -->
    <div v-if="emptyState" class="content report-empty">
      <i class="ti ti-info-circle" style="font-size: 32px; color: var(--t3)"></i>
      <p>请先从第一步选择要分析的活动或上传线下数据</p>
      <button class="btn pri" type="button" @click="router.push({ name: 'source', params: { type: 'online' } })">
        去选择活动
      </button>
    </div>

    <template v-else>
      <div class="content report-content">
        <!-- 信息头：真实选择数据 -->
        <section class="rph">
          <div style="font-size: 14px; font-weight: 600; display: flex; gap: 8px">
            <i class="ti ti-file-analytics" style="color: var(--primary)"></i>
            <span>{{ reportTitle }}</span>
          </div>
          <div style="display: flex; gap: 16px; margin-top: 8px; font-size: 12px; flex-wrap: wrap">
            <span><span style="color: var(--t3)">活动类型：</span>{{ headerInfo.typeName }}</span>
            <span v-if="headerInfo.period"><span style="color: var(--t3)">周期：</span>{{ headerInfo.period }}</span>
            <span v-if="headerInfo.fileName"><span style="color: var(--t3)">数据文件：</span>{{ headerInfo.fileName }}</span>
          </div>
          <div v-if="headerInfo.activityNames?.length" style="margin-top: 6px; font-size: 12px">
            <span style="color: var(--t3)">所选活动：</span>{{ headerInfo.activityNames.join('、') }}
          </div>
          <div class="chips">
            <span v-for="name in headerInfo.compNames" :key="name" class="chip">{{ name }}</span>
          </div>
        </section>

        <!-- 报告区 -->
        <section class="sc report-stage">
          <div class="sh">
            <i class="ti ti-report" style="color: var(--primary)"></i>
            <span class="stitle">分析报告</span>
            <span v-if="generating" style="font-size: 12px; color: var(--t3)">正在生成…</span>
          </div>
          <HtmlReportCard v-if="latestReport" :message="latestReport" :chat="chat" mode="stage" />
          <div v-else class="report-placeholder">
            <i class="ti ti-loader-2 spinning" style="font-size: 24px; color: var(--primary)"></i>
            <p>{{ bootError ? `生成失败：${bootError}，可在下方对话框重新发送需求` : '正在根据您选择的活动与分析框架生成报告，请稍候…' }}</p>
          </div>
        </section>

        <!-- AI 问答区 -->
        <section class="sc report-chat">
          <div class="sh">
            <i class="ti ti-message-question" style="color: var(--primary)"></i>
            <span class="stitle">AI报告问答</span>
          </div>
          <div ref="chatBody" class="report-chat-body">
            <ChatMessageList
              v-if="conversation"
              :chat="chat"
              :conversation="conversation"
              report-card-mode="slim"
              @focus-composer="composerRef?.focus()"
              @locate-report="scrollToReport"
            />
          </div>
          <ChatComposer
            v-if="conversation"
            ref="composerRef"
            :chat="chat"
            :conversation="conversation"
            @locate-trace="scrollToRunningTrace"
          />
        </section>
      </div>

      <div class="fbar">
        <button class="btn" type="button" @click="router.push({ name: 'compose' })">
          <i class="ti ti-arrow-left"></i> 返回调整
        </button>
        <button class="btn pri" type="button" :disabled="!latestReport" @click="exportReport">
          <i class="ti ti-download"></i> 导出HTML
        </button>
      </div>
    </template>

    <div v-if="reportExportOverlay.visible" class="report-export-overlay" role="status">
      <div class="report-export-loading">
        <i class="ti ti-loader-2 report-export-spinner"></i>
        <span>{{ reportExportOverlay.label }}</span>
        <small>请稍候，不要关闭当前页面</small>
      </div>
    </div>
  </div>
</template>
```

- 新增 scoped style（报告页布局适配，尺寸自定但风格对齐现有页面变量）：

```css
.report-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--t3); }
.report-chat-body { max-height: 420px; overflow-y: auto; padding: 4px 0; }
.report-placeholder { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 48px 0; color: var(--t3); font-size: 13px; }
.spinning { animation: report-spin 1s linear infinite; }
@keyframes report-spin { to { transform: rotate(360deg); } }
```

- 删除旧逻辑：`sendMessage` mock、`inlineTablerIconsCss`、`buildExportHtml`、`downloadReport`、`downloadBlob`，以及对 ChatPanel/ReportSummary 的引用。
- 删除文件：`components/common/ChatPanel.vue`、`components/report/ReportSummary.vue`、`components/report/BarChartList.vue`（先 `grep -rn` 确认无其他引用再删）。
- 注意 `useAgentChat` 的 options.urlParams 期望 `{ userId, userName, orgNo, srcSysNo, channel }`——`useChatUrlParams()` 返回值结构一致，直接传入。
- ChatMessageList/ChatComposer 的样式在 UiChatView 是满宽对话流，报告页问答区是普通卡片内嵌：`ChatMessageList` 内层样式多以 `.msg-row` 等类选择器定义，天然适配；若气泡宽度假设了对话页布局，微调 `.report-chat-body` 内边距即可，不改组件。

- [ ] **Step 2: 构建 + 全量测试**

```bash
cd frontend && npx vitest run && npm run build
```

Expected: PASS + build 成功。

- [ ] **Step 3: 端到端走查（Playwright 或手工）**

前置：`npm run dev` 运行中（端口 3000），后端运行中。

线上路径：
1. 打开 `http://localhost:3000/main` → 线上活动 → 勾选 2 个活动 → 下一步；
2. 编排组件页直接点"生成分析报告"；
3. 报告页：信息头显示所选活动与组件 chips；自动开始生成（问答区出现用户首条消息 + 思考面板流式更新）；
4. 生成完成后报告区 iframe 渲染报告；问答区出现 slim 卡片"报告已生成"；
5. 追问"总结一下活动效果"→ 正常流式回复；
6. 要求"把报告标题改成 XX"→ 出现审批卡 → 确认 → 报告区原地更新、slim 卡片显示 v2；
7. 点 slim 卡片"查看报告"→ 页面滚动到报告区；
8. 导出HTML → 下载文件正常；
9. 刷新页面 → 信息头/报告/对话全部恢复；若刷新时任务进行中 → 自动续传。

线下路径：
1. `/main` → 线下活动 → 选择 xlsx 文件真实上传 → 填日期 → 下一步 → 生成分析报告；
2. 报告页自动开始（首条消息含文件名与统计周期）→ 报告正常生成。

回归：`/chat-ui` 完整走查一遍（发消息、报告卡片、审批、上传、刷新恢复、导出）。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ReportView.vue frontend/src/components
git rm frontend/src/components/common/ChatPanel.vue frontend/src/components/report/ReportSummary.vue frontend/src/components/report/BarChartList.vue
git commit -m "报告页接入真实智能体：自动生成报告并支持对话交互"
```

---

## Self-Review 记录

- **Spec 覆盖**：决策表 5 项 → Task 1-8（完整对齐 + 复用）、Task 10 模板（保留布局）、Task 9（线下上传）、Task 10 `resetReportSession`/会话恢复（会话策略）。错误处理（断流/恢复/空态）→ Task 5 搬运 + Task 10 空态与 bootError。测试验证 → 各 Task 验证步骤 + Task 10 端到端走查。
- **已知取舍**：spec 中 composable 的 `onHtmlReport` 回调与 `reportCardMode` option 在实施中简化为 ReportView 的 `latestReport` computed + ChatMessageList 的 `reportCardMode` prop（等价且更简单）；`scrollToRunningTrace` 在两个视图各留一份（操作各自 DOM）。

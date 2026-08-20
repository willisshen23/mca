import { computed, nextTick, onMounted, onBeforeUnmount } from 'vue';
import {
  shouldDisplayThinkingTrace,
  stepStatusText,
  syncTracePlan,
  finishThinkingTrace,
  visibleTraceSteps,
  traceProgressText,
  thinkingTitleText,
  traceDisplayName,
  upsertTraceStep
} from '@/utils/agentTrace.js';
import {
  compactActivity,
  compactTracePayload,
  activityId,
  activityRowNumber,
  selectionActivities,
  selectedActivityRowNumbers,
  toggleActivitySelectionPure
} from '@/utils/activityFormat.js';
import { stripReportFooterNote } from '@/utils/htmlReport.js';
import {
  fetchConversationMessages,
  createConversationAPI,
  renameConversationAPI,
  getUserId
} from '@/api/conversations.js';
import {
  runAgentV2,
  cancelAgentV2,
  resumeAgentV2,
  getAgentV2RunStatus,
  attachAgentV2Run
} from '@/api/agentRun.js';
import { submitReportFeedback, reportDownloadUrl } from '@/api/agentRunHistory.js';
import { API_BASE } from '@/api/base.js';

// 会话状态、消息持久化、思维链状态、报告消息、活动选择、审批与反馈，
// 以及流式对话引擎（sendMessage/consumeAgentStream/recover/cancel/审批恢复）。
export function useAgentChat(options = {}) {
  const SYSTEM_BUSY_MESSAGE = '系统繁忙，请稍后再试';
  const TRANSPORT_ERROR_MARKERS = [
    'failed to fetch',
    'network error',
    'networkerror',
    'load failed',
    'fetch failed',
    'timed out',
    'timeout',
    'terminated',
    'connection reset',
    'connection closed',
    '请求超时',
    '网络异常',
    '网络错误',
    '连接中断',
    '连接已关闭'
  ];

  function isTransportError(error) {
    const name = String(error?.name || '').toLowerCase();
    const message = String(error?.message || error || '').toLowerCase();
    return name === 'aborterror'
      || name === 'timeouterror'
      || TRANSPORT_ERROR_MARKERS.some((marker) => message.includes(marker));
  }

  function requestErrorMessage(error, prefix = '请求失败：') {
    if (isTransportError(error)) return SYSTEM_BUSY_MESSAGE;
    return `${prefix}${error?.message || error || '未知错误'}`;
  }

  const STORAGE_PREFIX = 'chat_dynamic_messages:';
  const RUN_SEQUENCE_PREFIX = 'agent_run_sequence:';

  // 页面卸载标记：全页面唯一一套（持久化与流式引擎共用），
  // 刷新/离开页面时流式消费不再写入兜底错误消息。
  let pageUnloading = false;
  function handlePageExit() {
    pageUnloading = true;
  }

  function handlePageShow() {
    pageUnloading = false;
  }

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

  function storageKey(conversationId) {
    return `${STORAGE_PREFIX}${conversationId}`;
  }

  function runSequenceKey(conversationId) {
    return `${RUN_SEQUENCE_PREFIX}${conversationId}`;
  }

  function getRunSequence(conversationId) {
    return Math.max(0, Number(localStorage.getItem(runSequenceKey(conversationId))) || 0);
  }

  function setRunSequence(conversationId, sequence) {
    try {
      localStorage.setItem(runSequenceKey(conversationId), String(Math.max(0, sequence || 0)));
    } catch (e) {
      console.warn('保存任务续传位置失败', e);
    }
  }

  function compactMessageForStorage(message = {}) {
    if (message.role === 'execution_trace') {
      return {
        role: 'execution_trace',
        expanded: message.expanded,
        status: message.status,
        startedAt: message.startedAt,
        durationMs: message.durationMs,
        payload: compactTracePayload(message.payload || {}),
        steps: Array.isArray(message.steps)
          ? message.steps.map((step) => ({
              node: step.node,
              displayName: step.displayName,
              message: step.message,
              status: step.status,
              timestamp: step.timestamp,
              fromPlan: step.fromPlan,
              skipReason: step.skipReason || '',
              payload: compactTracePayload(step.payload || {})
            }))
          : []
      };
    }
    if (message.role === 'approval_request') {
      if (message.resolved) return null;
      return {
        role: 'approval_request',
        tool: message.tool,
        displayName: message.displayName,
        args: message.args,
        activities: message.activities || [],
        description: message.description,
        allowedDecisions: message.allowedDecisions,
        resolved: false,
        decision: null
      };
    }
    if (message.role === 'html_report') {
      return null;
    }
    return {
      role: message.role,
      text: message.text,
      ...(message.transportFallback ? { transportFallback: true } : {}),
      ...(isDownloadableExportMessage(message)
        ? { exportArtifact: message.exportArtifact }
        : {}),
      ...(message.role === 'user' && Array.isArray(message.selectedRows) && message.selectedRows.length
        ? { selectedRows: message.selectedRows }
        : {}),
      ...(message.role === 'ai' && Array.isArray(message.selectableActivities)
        ? {
            selectableActivities: message.selectableActivities.map(compactActivity),
            selectedIds: message.selectedIds || []
          }
        : {})
    };
  }

  function persistConversation(conversation = options.getConversation?.()) {
    if (!conversation?.id) return;
    try {
      const messages = (conversation.dynamicMessages || [])
        .map(compactMessageForStorage)
        .filter(Boolean);
      localStorage.setItem(storageKey(conversation.id), JSON.stringify(messages));
    } catch (e) {
      console.warn('保存对话过程失败', e);
    }
  }

  function restoreConversationMessages(conversation) {
    if (!conversation?.id) return false;
    try {
      const raw = localStorage.getItem(storageKey(conversation.id));
      if (!raw) return false;
      const messages = JSON.parse(raw);
      if (!Array.isArray(messages) || messages.length === 0) return false;
      conversation.dynamicMessages = messages.filter((message) => (
        message?.role !== 'activity_selection'
        && (message?.role !== 'execution_trace' || shouldDisplayThinkingTrace(message))
      ));
      return true;
    } catch (e) {
      console.warn('恢复对话过程失败', e);
      return false;
    }
  }

  function parseUserSelectionContent(content) {
    const source = String(content || '');
    const match = source.match(/^已选择第\s*([\d\s、,，]+)\s*行(?:\r?\n)?/);
    if (!match) return { text: source, selectedRows: [] };
    const selectedRows = match[1]
      .split(/[、,，\s]+/)
      .map((value) => Number(value))
      .filter((value) => Number.isInteger(value) && value > 0);
    return {
      text: source.slice(match[0].length).trim(),
      selectedRows
    };
  }

  function addMessage(role, text, conversation = options.getConversation?.(), metadata = {}) {
    const message = { role, text, ...metadata };
    conversation.dynamicMessages.push(message);
    if (role === 'user' && conversation.title.startsWith('新建分析对话')) {
      const titleText = text || (
        Array.isArray(metadata.selectedRows) && metadata.selectedRows.length
          ? `已选择第 ${metadata.selectedRows.join('、')} 行`
          : ''
      );
      conversation.title = titleText.slice(0, 18);
    }
    persistConversation(conversation);
    options.onScroll?.(conversation);
    return message;
  }

  function downloadExportArtifact(artifact) {
    if (!artifact?.download_url) return;
    const link = document.createElement('a');
    link.href = `${API_BASE}${artifact.download_url}`;
    link.download = artifact.file_name || `report.${artifact.format || 'html'}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  function isDownloadableExportMessage(message = {}) {
    const artifact = message.exportArtifact;
    return message.role === 'ai'
      && artifact?.kind === 'report_export'
      && String(artifact.format || '').toLowerCase() === 'html'
      && Boolean(artifact.download_url);
  }

  function addHtmlReport(html, conversation = options.getConversation?.(), payload = {}, insertIndex = null) {
    if (!html) return;
    const reportContext = payload.report_context || payload.reportContext || null;
    const requestId = payload.request_id || payload.requestId || '';
    const versionNo = payload.version_no ?? payload.versionNo ?? reportContext?.version_no ?? null;
    // 报告的真实 request_id（运行历史/反馈用）；requestId 仅是卡片标识，
    // 直播时它是对话轮次 ID，恢复的旧版本卡片会加 -vN 后缀，二者不能混用。
    const reportRequestId = payload.report_request_id || reportContext?.request_id || requestId;
    // 报告被修改（同一 request_id 产生新版本）时原地更新既有报告消息，
    // 反馈随版本重置为空；不同 request_id 视为新报告，追加新消息。
    const existing = requestId
      ? conversation.dynamicMessages.find((message) => message.role === 'html_report' && message.requestId === requestId)
      : null;
    if (existing) {
      if (existing.html === html && (versionNo === null || existing.versionNo === versionNo)) {
        return;
      }
      existing.html = html;
      existing.versionNo = versionNo ?? existing.versionNo ?? null;
      existing.reportRequestId = reportRequestId || existing.reportRequestId;
      existing.reportContext = reportContext || existing.reportContext || null;
      existing.feedback = '';
      existing.feedbackComment = '';
      existing.feedbackError = '';
      existing.feedbackSaving = false;
      existing.commentEditorOpen = false;
      existing.feedbackCommentDraft = '';
      persistConversation(conversation);
      options.onScroll?.(conversation);
      return;
    }
    if (conversation.dynamicMessages.some((message) => message.role === 'html_report' && message.html === html)) {
      return;
    }
    const message = {
      role: 'html_report',
      title: '活动分析报告',
      html,
      requestId,
      reportRequestId,
      versionNo,
      reportContext,
      feedback: payload.report_feedback || '',
      feedbackComment: payload.feedback_comment || '',
      feedbackSaving: false,
      feedbackError: '',
      commentEditorOpen: false,
      feedbackCommentDraft: ''
    };
    if (Number.isInteger(insertIndex) && insertIndex >= 0 && insertIndex < conversation.dynamicMessages.length) {
      conversation.dynamicMessages.splice(insertIndex, 0, message);
    } else {
      conversation.dynamicMessages.push(message);
    }
    persistConversation(conversation);
    options.onScroll?.(conversation);
  }

  function hasRunningThinking(conversation = options.getConversation?.()) {
    return Boolean(conversation?.dynamicMessages?.some((message) => (
      message.role === 'execution_trace' && message.status === 'running'
    )));
  }

  function ensureThinkingTrace(conversation, startedAt) {
    let trace = conversation.dynamicMessages.find((message) => (
      message.role === 'execution_trace' && message.status === 'running'
    ));
    if (!trace) {
      trace = {
        role: 'execution_trace',
        steps: [],
        payload: {},
        expanded: true,
        status: 'running',
        startedAt,
        durationMs: 0
      };
      conversation.dynamicMessages.push(trace);
    }
    return trace;
  }

  function resumePausedThinkingTrace(conversation = options.getConversation?.()) {
    const trace = [...(conversation?.dynamicMessages || [])].reverse().find((message) => (
      message.role === 'execution_trace' && message.status === 'paused'
    ));
    if (!trace) return null;
    // 审批恢复属于同一次执行，继续复用原 trace，避免额外生成空的“已思考 0/N”面板。
    trace.status = 'running';
    trace.expanded = true;
    trace.startedAt = Date.now();
    trace.durationMs = 0;
    trace.steps?.forEach((step) => {
      if (step.status === 'skipped' && step.skipReason === '后续步骤将在选择活动后继续执行') {
        step.status = 'pending';
        step.skipReason = '';
        step.message = stepStatusText('pending');
      }
    });
    return trace;
  }

  function finishRunningThinking(conversation = options.getConversation?.(), payload = {}) {
    const trace = conversation?.dynamicMessages?.find((message) => (
      message.role === 'execution_trace' && message.status === 'running'
    ));
    finishThinkingTrace(trace, payload);
  }

  function addRuntimeTrace(runtimeTrace, conversation = options.getConversation?.()) {
    if (!runtimeTrace?.plan || !Array.isArray(runtimeTrace.plan) || runtimeTrace.plan.length === 0) return;
    let trace = conversation.dynamicMessages.find((message) => message.role === 'execution_trace');
    if (!trace) {
      trace = {
        role: 'execution_trace',
        steps: [],
        payload: {},
        expanded: true,
        status: 'running',
        startedAt: Date.now(),
        durationMs: 0
      };
      conversation.dynamicMessages.push(trace);
    }
    trace.payload = {
      ...(trace.payload || {}),
      ...(runtimeTrace.payload || {})
    };
    trace.status = runtimeTrace.status || trace.status || 'done';
    trace.expanded = runtimeTrace.expanded ?? trace.status === 'running';
    trace.durationMs = trace.durationMs || 0;
    syncTracePlan(trace, runtimeTrace.plan, runtimeTrace.payload || {});
    conversation.typing = trace.status === 'running';
    persistConversation(conversation);
  }

  function restoredReportPayload(detail = {}) {
    return {
      ...(detail.reportHistory || {}),
      report_context: detail.reportContext || null
    };
  }

  // 报告卡片的原始位置：产生它的用户轮次之后、下一轮用户消息之前。
  function findReportInsertIndex(messages, userOrdinal) {
    let seen = -1;
    for (let i = 0; i < messages.length; i++) {
      if (messages[i].role !== 'user') continue;
      seen++;
      if (seen === userOrdinal) {
        for (let j = i + 1; j < messages.length; j++) {
          if (messages[j].role === 'user') return j;
        }
        return messages.length;
      }
    }
    return messages.length;
  }

  // 刷新/切换会话后按原位置恢复全部报告卡片。
  // 直播时每产生一份报告（含每次修改出的新版本）都会追加一张卡片，
  // 因此恢复也按 报告 × 版本 逐份取回；最新报告的最新版本
  // 复用 checkpoint 里的 htmlReport（保留反馈等上下文）。
  async function restoreConversationReports(detail, conv) {
    if (!detail || Array.isArray(detail)) return;
    const histories = Array.isArray(detail.reportHistories) ? detail.reportHistories : [];
    const htmlReport = detail.htmlReport || '';
    if (!histories.length) {
      if (htmlReport) {
        addHtmlReport(htmlReport, conv, restoredReportPayload(detail));
      }
      return;
    }
    const lastRequestId = histories[histories.length - 1]?.request_id || '';
    //  placements 由后端按版本创建时间锚定到用户轮次；缺失时退化为顺序追加
    const placements = Array.isArray(detail.reportPlacements) && detail.reportPlacements.length
      ? detail.reportPlacements
      : histories.flatMap((item) => {
          const versions = Array.isArray(item.version_numbers) && item.version_numbers.length
            ? item.version_numbers
            : [item.version_no || item.latest_version_no || 1];
          return versions.map((versionNo) => ({ request_id: item.request_id, version_no: versionNo, user_turn: -1 }));
        });
    for (const placement of placements) {
      const item = histories.find((h) => h.request_id === placement.request_id);
      if (!item?.id) continue;
      const versions = Array.isArray(item.version_numbers) && item.version_numbers.length
        ? item.version_numbers
        : [item.version_no || item.latest_version_no || 1];
      const isLastVersion = placement.request_id === lastRequestId
        && placement.version_no === versions[versions.length - 1];
      const insertIndex = placement.user_turn >= 0
        ? findReportInsertIndex(conv.dynamicMessages, placement.user_turn)
        : conv.dynamicMessages.length;
      // 最新报告的最新版本用 checkpoint 内容恢复
      if (isLastVersion && htmlReport) {
        addHtmlReport(htmlReport, conv, { ...restoredReportPayload(detail), version_no: placement.version_no }, insertIndex);
        continue;
      }
      try {
        const response = await fetch(reportDownloadUrl(item.id, 'html', placement.version_no));
        if (!response.ok) continue;
        const html = stripReportFooterNote(await response.text());
        // checkpoint 没有报告时，最后一张卡片保留真实 request_id（后续修改用）
        const keepRealId = isLastVersion && !htmlReport;
        // 每个版本有各自独立的反馈，不能沿用 item.report_feedback（那是最新版本的）
        const versionInfo = (Array.isArray(item.versions) ? item.versions : [])
          .find((v) => v.version_no === placement.version_no);
        // 历史版本作为独立卡片恢复：request_id 加版本后缀，避免被当作同一份报告原地更新
        addHtmlReport(html, conv, {
          ...item,
          request_id: keepRealId ? item.request_id : `${item.request_id}-v${placement.version_no}`,
          report_request_id: item.request_id,
          version_no: placement.version_no,
          report_feedback: versionInfo?.feedback || '',
          feedback_comment: versionInfo?.feedback_comment || ''
        }, insertIndex);
      } catch (e) {
        console.warn('恢复历史报告失败', e);
      }
    }
  }

  function pruneEmptyCompletedTraces(conversation = options.getConversation?.()) {
    if (!Array.isArray(conversation?.dynamicMessages)) return;
    conversation.dynamicMessages = conversation.dynamicMessages.filter((message) => (
      message?.role !== 'execution_trace' || shouldDisplayThinkingTrace(message)
    ));
  }

  // 封装原 switchConversation 中 conv.dynamicMessages.length === 0 的恢复分支。
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

  function attachActivitySelection(message, activities, conversation = options.getConversation?.()) {
    if (!message || !Array.isArray(activities) || activities.length === 0) return;
    // 清理旧版本保存在会话里的重复选择卡片。
    for (let index = conversation.dynamicMessages.length - 1; index >= 0; index -= 1) {
      if (conversation.dynamicMessages[index]?.role === 'activity_selection') {
        conversation.dynamicMessages.splice(index, 1);
      }
    }
    message.selectableActivities = activities.map(compactActivity);
    message.selectedIds = [];
    persistConversation(conversation);
    options.onScroll?.(conversation);
  }

  function toggleActivitySelection(message, activity) {
    toggleActivitySelectionPure(message, activity);
    persistConversation();
  }

  function setAllActivityRows(message, checked) {
    // 批量选择某张表时，清空其他查询表的草稿选择，避免行号来源混淆。
    for (const item of options.getConversation?.()?.dynamicMessages || []) {
      if (item !== message && item.role === 'ai' && Array.isArray(item.selectableActivities)) {
        item.selectedIds = [];
      }
    }
    message.selectedIds = checked
      ? selectionActivities(message).map((activity) => activityId(activity)).filter(Boolean)
      : [];
    persistConversation();
  }

  function removeComposerSelectedRow(rowNumber) {
    const message = composerSelectionMessage.value;
    if (!message) return;
    const activity = selectionActivities(message).find(
      (item, index) => activityRowNumber(item, index) === rowNumber
    );
    if (activity) toggleActivitySelection(message, activity);
  }

  function addApprovalRequest(payload, conversation = options.getConversation?.()) {
    if (!conversation) return;
    const existing = conversation.dynamicMessages.some(
      (message) => message.role === 'approval_request' && !message.resolved
    );
    if (existing) return;
    conversation.dynamicMessages.push({
      role: 'approval_request',
      tool: payload.tool,
      displayName: payload.display_name || payload.tool,
      args: payload.args || {},
      editedArgs: JSON.stringify(payload.args || {}, null, 2),
      activities: payload.activities || [],
      description: payload.description || '',
      allowedDecisions: payload.allowed_decisions || ['approve', 'reject'],
      resolved: false,
      decision: null,
      expanded: true,
      editing: false,
      editError: ''
    });
    conversation.typing = false;
    persistConversation(conversation);
    options.onScroll?.(conversation);
  }

  function formatApprovalArgs(args = {}) {
    const entries = Object.entries(args).filter(([, value]) => value !== undefined && value !== '');
    if (entries.length === 0) return '无参数';
    return entries.map(([key, value]) => {
      let display = value;
      if (Array.isArray(value)) display = value.join('、');
      else if (typeof value === 'object') display = JSON.stringify(value);
      return `${key}：${display}`;
    }).join('；');
  }

  function formatApprovalDescription(message = {}) {
    if (message.tool === 'modify_report') {
      const args = message.args || {};
      const parts = [];
      const contentChanges = args.content_changes || [];
      if (contentChanges.length) {
        parts.push(`内容修改：${contentChanges.join('；')}`);
      }
      const chartReplacements = args.chart_replacements || [];
      if (chartReplacements.length) {
        const items = chartReplacements.map((item) => {
          const cid = item?.chart_id || '未指定';
          const toType = item?.to_chart_type || '未指定';
          return `将 ${cid} 替换为 ${toType}`;
        });
        parts.push(`图表替换：${items.join('；')}`);
      }
      const styleChanges = args.style_changes || [];
      if (styleChanges.length) {
        parts.push(`样式调整：${styleChanges.join('；')}`);
      }
      if (args.free_instruction) {
        parts.push(`其他要求：${args.free_instruction}`);
      }
      return parts.length ? parts.join('\n') : '无具体修改说明';
    }
    return formatApprovalArgs(message.args);
  }

  async function submitReportFeedbackToServer(message, feedback, comment) {
    const threadId = options.getConversation?.()?.id || '';
    message.feedbackSaving = true;
    message.feedbackError = '';
    try {
      const submitOptions = {};
      if (message.versionNo !== undefined && message.versionNo !== null) {
        submitOptions.versionNo = message.versionNo;
      }
      if (comment) {
        submitOptions.comment = comment;
      }
      const saved = await submitReportFeedback(message.reportRequestId || message.requestId, feedback, threadId, submitOptions);
      message.feedback = saved.report_feedback || (feedback === 'none' ? '' : feedback);
      if (saved.version_no !== undefined && saved.version_no !== null) {
        message.versionNo = saved.version_no;
      }
      message.feedbackComment = message.feedback === 'dislike' ? (saved.feedback_comment || comment || '') : '';
      if (saved.request_id) {
        message.reportRequestId = saved.request_id;
      }
    } catch (e) {
      message.feedbackError = e.message || '反馈保存失败';
    } finally {
      message.feedbackSaving = false;
    }
  }

  async function handleReportFeedback(message, feedback) {
    const threadId = options.getConversation?.()?.id || '';
    if ((!message?.requestId && !threadId) || message.feedbackSaving) return;
    // 再次点击同值 = 取消反馈
    if (message.feedback === feedback) {
      message.commentEditorOpen = false;
      await submitReportFeedbackToServer(message, 'none');
      return;
    }
    // 点踩先弹出原因输入（选填，可跳过直接提交）
    if (feedback === 'dislike') {
      message.feedbackCommentDraft = message.feedbackComment || '';
      message.commentEditorOpen = true;
      return;
    }
    message.commentEditorOpen = false;
    await submitReportFeedbackToServer(message, 'like');
  }

  async function submitDislikeFeedback(message, skip = false) {
    const draft = skip ? '' : String(message.feedbackCommentDraft || '').trim();
    if (draft.length > 500) {
      message.feedbackError = '点踩原因不能超过 500 字';
      return;
    }
    message.commentEditorOpen = false;
    await submitReportFeedbackToServer(message, 'dislike', draft || undefined);
  }

  function canSubmitReportFeedback(message) {
    return Boolean(message?.requestId || options.getConversation?.()?.id);
  }

  function removeStaleTransportFallback(conversation) {
    const messages = conversation?.dynamicMessages || [];
    let lastUserIndex = -1;
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index]?.role === 'user') {
        lastUserIndex = index;
        break;
      }
    }
    const filtered = messages.filter((message, index) => !(
      index > lastUserIndex
      && message.role === 'ai'
      && message.text === SYSTEM_BUSY_MESSAGE
    ));
    if (filtered.length !== messages.length) {
      conversation.dynamicMessages = filtered;
      persistConversation(conversation);
    }
  }

  // ---- 流式对话引擎（自 UiChatView 迁入）----

  const recoveringRunThreads = new Set();

  async function recoverAgentRun(conversation) {
    if (!conversation?.id || recoveringRunThreads.has(conversation.id)) return;
    recoveringRunThreads.add(conversation.id);
    try {
      const after = getRunSequence(conversation.id);
      const status = await getAgentV2RunStatus(conversation.id);
      if (!status?.exists) {
        if (hasRunningThinking(conversation)) {
          finishRunningThinking(conversation, { message: '任务已中断' });
          persistConversation(conversation);
        }
        return;
      }
      if (!status.active && Number(status.last_seq || 0) <= after) return;

      removeStaleTransportFallback(conversation);
      conversation.typing = true;
      const response = await attachAgentV2Run(conversation.id, after);
      if (!response.ok) throw new Error(`恢复任务失败：${response.status}`);
      await consumeAgentStream(response, conversation, { recovery: true });
    } catch (e) {
      conversation.typing = false;
      console.warn('恢复正在执行的任务失败', e);
    } finally {
      recoveringRunThreads.delete(conversation.id);
    }
  }

  async function reconnectAgentStream(conversation, streamOptions = {}) {
    if (pageUnloading || (streamOptions.reconnectAttempts || 0) >= 2) return pageUnloading;
    try {
      const after = getRunSequence(conversation.id);
      const status = await getAgentV2RunStatus(conversation.id);
      if (!status?.exists || (!status.active && Number(status.last_seq || 0) <= after)) {
        return false;
      }
      const response = await attachAgentV2Run(conversation.id, after);
      if (!response.ok) return false;
      await consumeAgentStream(response, conversation, {
        ...streamOptions,
        recovery: true,
        reconnectAttempts: (streamOptions.reconnectAttempts || 0) + 1
      });
      return true;
    } catch (e) {
      console.warn('任务流自动续接失败', e);
      return false;
    }
  }

  async function consumeAgentStream(response, conversation, streamOptions = {}) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const executionSteps = [];
    let pendingHtmlReport = '';
    let pendingReportPayload = {};
    let reportGuardRejected = false;
    let reportUpdatedThisTurn = false;
    let pendingActivityList = [];
    let pendingExportArtifact = null;
    const thinkingStartedAt = Date.now();

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split('\n\n');
        buffer = chunks.pop() || '';

        for (const chunk of chunks) {
          const lines = chunk.split('\n');
          const eventIdLine = lines.find((line) => line.startsWith('id:'));
          const eventSequence = eventIdLine ? Number(eventIdLine.slice(3).trim()) : 0;
          const dataLines = lines.filter((line) => line.startsWith('data:'));
          if (dataLines.length === 0) continue;

          const dataStr = dataLines.map((line) => line.slice(5).trim()).join('');
          if (dataStr === '[DONE]') continue;

          try {
            const event = JSON.parse(dataStr);
            if (eventSequence > 0) setRunSequence(conversation.id, eventSequence);
            if (event.type === 'node_update') {
              if (event.payload?.export_artifact) {
                pendingExportArtifact = event.payload.export_artifact;
              }
              if (event.payload?.html_report) {
                reportUpdatedThisTurn = true;
              }
              if (Array.isArray(event.payload?.activity_list) && event.payload.activity_list.length > 0) {
                pendingActivityList = event.payload.activity_list;
              }
              if (!event.progress_message) continue;
              const stepInfo = {
                node: event.node,
                displayName: traceDisplayName(event.node, event.node_display_name || event.node),
                message: event.progress_message,
                payload: event.payload || {},
                timestamp: Date.now(),
                fromPlan: false
              };
              executionSteps.push(stepInfo);
              const trace = ensureThinkingTrace(conversation, thinkingStartedAt);
              syncTracePlan(trace, event.payload?.plan, event.payload || {});
              upsertTraceStep(trace, {
                ...stepInfo,
                status: event.payload?.tool_status === 'running'
                  ? 'running'
                  : (event.payload?.plan?.find((item) => item.step === event.node)?.status || 'done')
              });
              trace.durationMs = Date.now() - (trace.startedAt || thinkingStartedAt);

              if (event.payload?.report_html_guard_result?.valid === false) {
                reportGuardRejected = true;
                pendingHtmlReport = '';
                pendingReportPayload = {};
              } else if (event.payload?.html_report) {
                pendingHtmlReport = event.payload.html_report;
                pendingReportPayload = event.payload || {};
              }
              persistConversation(conversation);
              options.onScroll?.(options.getConversation?.());
            } else if (event.type === 'approval_required') {
              conversation.typing = false;
              finishRunningThinking(conversation, { awaiting_approval: true });
              addApprovalRequest(event.payload, conversation);
            } else if (event.type === 'done') {
              const reply = event.payload?.final_response || '分析完成。';
              conversation.typing = false;
              if (event.payload?.report_html_guard_result?.valid === false) {
                reportGuardRejected = true;
                pendingHtmlReport = '';
                pendingReportPayload = {};
              }
              const reportUpdated = Boolean(event.payload?.report_updated || reportUpdatedThisTurn);
              const htmlReport = reportUpdated
                ? (event.payload?.html_report || (reportGuardRejected ? '' : pendingHtmlReport))
                : '';
              const reportPayload = reportUpdated && event.payload?.html_report
                ? (event.payload || {})
                : pendingReportPayload;
              const runningTrace = conversation.dynamicMessages.find((message) => (
                message.role === 'execution_trace' && message.status === 'running'
              ));

              if (executionSteps.length > 0) {
                if (runningTrace) {
                  syncTracePlan(runningTrace, event.payload?.plan, event.payload || {});
                  finishThinkingTrace(runningTrace, event.payload || {});
                } else {
                  const traceSteps = [];
                  const finalTrace = { steps: traceSteps };
                  syncTracePlan(finalTrace, event.payload?.plan, event.payload || {});
                  executionSteps.forEach((step) => upsertTraceStep(finalTrace, step));
                  conversation.dynamicMessages.push({
                    role: 'execution_trace',
                    steps: traceSteps.length ? traceSteps : executionSteps,
                    payload: event.payload || {},
                    expanded: false,
                    status: 'done',
                    startedAt: thinkingStartedAt,
                    durationMs: Date.now() - thinkingStartedAt
                  });
                }
              }
              pruneEmptyCompletedTraces(conversation);

              const replyAlreadyRestored = streamOptions.recovery && conversation.dynamicMessages.some(
                (message) => message.role === 'ai' && message.text === reply
              );
              const replyMessage = !event.payload?.awaiting_approval && !replyAlreadyRestored
                ? addMessage('ai', reply, conversation, {
                  ...(event.payload?.export_artifact || pendingExportArtifact
                    ? { exportArtifact: event.payload?.export_artifact || pendingExportArtifact }
                    : {})
                })
                : null;
              const selectableActivities = event.payload?.activity_list || pendingActivityList;
              if (replyMessage && !reportUpdated && Array.isArray(selectableActivities) && selectableActivities.length > 0) {
                attachActivitySelection(replyMessage, selectableActivities, conversation);
              }
              if (htmlReport) {
                addHtmlReport(htmlReport, conversation, reportPayload);
              }
              return;
            } else if (event.type === 'error') {
              conversation.typing = false;
              finishRunningThinking(conversation, event.payload || {});
              addMessage(
                'ai',
                requestErrorMessage(event.payload?.message || '未知错误', '出错了：'),
                conversation
              );
              return;
            } else if (event.type === 'cancelled') {
              conversation.typing = false;
              finishRunningThinking(conversation);
              addMessage('ai', '任务已取消。', conversation);
              return;
            }
          } catch (e) {
            // 忽略解析失败的行
          }
        }
      }

      // 未收到 done 就断流时，先尝试从服务端游标续接；刷新离开页面时不写错误消息。
      if (pageUnloading) return;
      if (await reconnectAgentStream(conversation, streamOptions)) return;
      conversation.typing = false;
      const fallbackRunningTrace = conversation.dynamicMessages.find((message) => (
        message.role === 'execution_trace' && message.status === 'running'
      ));
      if (fallbackRunningTrace) {
        finishRunningThinking(conversation);
      }
      addMessage('ai', SYSTEM_BUSY_MESSAGE, conversation, { transportFallback: true });
    } catch (e) {
      if (pageUnloading) return;
      if (isTransportError(e) && await reconnectAgentStream(conversation, streamOptions)) return;
      conversation.typing = false;
      finishRunningThinking(conversation);
      const errorMessage = requestErrorMessage(e);
      addMessage('ai', errorMessage, conversation, {
        transportFallback: errorMessage === SYSTEM_BUSY_MESSAGE
      });
    }
  }

  async function sendMessage({ text = '', uploadedFile = null, selectedRows = [], reportComponents = [], conversation = options.getConversation?.() } = {}) {
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
        channel: options.urlParams?.channel,
        reportComponents
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

  async function cancelRun(conversation = options.getConversation?.()) {
    if (!conversation || !conversation.typing) return;

    try {
      await cancelAgentV2(conversation.id);
    } catch (e) {
      console.error('取消请求失败', e);
    }
  }

  async function resolveApproval(message, decision, editedArgs = null) {
    if (message.resolved) return;
    const conversation = options.getConversation?.();
    let finalEditedArgs = {};
    if (decision === 'edit') {
      try {
        finalEditedArgs = editedArgs !== null ? editedArgs : JSON.parse(message.editedArgs || '{}');
      } catch (e) {
        message.editError = '参数 JSON 格式错误：' + e.message;
        return;
      }
    }
    message.resolved = true;
    message.decision = decision;
    message.expanded = false;
    message.editError = '';
    const resumedTrace = resumePausedThinkingTrace(conversation);
    persistConversation();

    conversation.typing = true;
    setRunSequence(conversation.id, 0);
    try {
      const response = await resumeAgentV2({
        threadId: conversation.id,
        decision,
        tool: message.tool,
        editedArgs: finalEditedArgs,
        message: '',
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

      await consumeAgentStream(response, conversation, { isResume: true });
    } catch (e) {
      conversation.typing = false;
      if (resumedTrace) {
        resumedTrace.status = 'paused';
        resumedTrace.expanded = true;
      }
      message.resolved = false;
      message.decision = null;
      message.expanded = true;
      persistConversation();
      addMessage('ai', requestErrorMessage(e, '审批恢复失败：'), conversation);
    }
  }

  // 计算属性
  const composerSelectionMessage = computed(() => (
    [...(options.getConversation?.()?.dynamicMessages || [])].reverse().find((message) => (
      message.role === 'ai'
      && Array.isArray(message.selectableActivities)
      && (message.selectedIds || []).length > 0
    )) || null
  ));
  const composerSelectedRows = computed(() => (
    composerSelectionMessage.value ? selectedActivityRowNumbers(composerSelectionMessage.value) : []
  ));
  const hasPendingApproval = computed(() =>
    options.getConversation?.()?.dynamicMessages?.some(
      (message) => message.role === 'approval_request' && !message.resolved
    )
  );
  // 当前运行中 thinking trace 的快照，用于底部浮动进度指示器
  const currentRunningTraceSnapshot = computed(() => {
    const conversation = options.getConversation?.();
    if (!conversation?.typing) return null;
    const trace = conversation.dynamicMessages?.find((message) => (
      message.role === 'execution_trace' && message.status === 'running'
    ));
    if (!trace) return null;
    const steps = visibleTraceSteps(trace);
    const currentStep = steps.find((step) => step.status === 'running');
    return {
      title: thinkingTitleText(trace),
      progressText: traceProgressText(trace),
      currentStepName: currentStep?.displayName || currentStep?.node || '处理中',
      currentStepMessage: currentStep?.message || '',
      trace
    };
  });

  return {
    // 工厂
    createConversationState,
    // 消息与持久化
    addMessage,
    persistConversation,
    restoreConversationMessages,
    parseUserSelectionContent,
    removeStaleTransportFallback,
    // 思维链状态
    finishRunningThinking,
    hasRunningThinking,
    addRuntimeTrace,
    pruneEmptyCompletedTraces,
    // 报告消息
    addHtmlReport,
    isDownloadableExportMessage,
    downloadExportArtifact,
    restoreConversationReports,
    loadConversation,
    // 活动选择
    toggleActivitySelection,
    setAllActivityRows,
    attachActivitySelection,
    removeComposerSelectedRow,
    // 审批
    addApprovalRequest,
    formatApprovalArgs,
    formatApprovalDescription,
    // 反馈
    submitReportFeedbackToServer,
    handleReportFeedback,
    submitDislikeFeedback,
    canSubmitReportFeedback,
    // 计算属性
    composerSelectionMessage,
    composerSelectedRows,
    hasPendingApproval,
    currentRunningTraceSnapshot,
    // 流式对话引擎
    sendMessage,
    cancelRun,
    resolveApproval,
    consumeAgentStream,
    recoverAgentRun,
    // run 游标
    getRunSequence,
    setRunSequence
  };
}

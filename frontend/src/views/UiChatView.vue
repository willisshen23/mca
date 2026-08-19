<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import {
  fetchConversations,
  createConversationAPI,
  deleteConversationAPI,
  renameConversationAPI,
  fetchConversationMessages,
  getUserId
} from '@/api/conversations.js';
import { submitReportFeedback, reportDownloadUrl } from '@/api/agentRunHistory.js';
import {
  runAgentV2,
  cancelAgentV2,
  resumeAgentV2,
  getAgentV2RunStatus,
  attachAgentV2Run
} from '@/api/agentRun.js';
import { API_BASE } from '@/api/base.js';
import { uploadFile } from '@/api/files.js';
import { fetchQuickPrompts } from '@/api/quickPrompts.js';
import { useChatUrlParams } from '@/composables/useChatUrlParams';
import { activityStatusTone, displayActivityStatus, displayActivityType, replaceActivityStatusCodes } from '@/utils/activityDictionaries.js';
import {
  activityName, activityId, activityRowNumber, activityPeriod, activityTags,
  activitySummary, visibleActivities, compactActivity, compactTemplate,
  compactTracePayload, selectionActivities, allActivitySelectionChecked,
  selectedActivityRowNumbers, toggleActivitySelectionPure
} from '@/utils/activityFormat.js';
import { renderMarkdown } from '@/utils/markdown.js';
import {
  visibleTraceSteps, traceProgressText, thinkingTitleText, shouldDisplayThinkingTrace,
  stepKey, traceDisplayName, isTraceNode, isPendingStep, stepStatusText,
  upsertTraceStep, syncTracePlan, finishThinkingTrace,
  showTemplateMatchDetail, showTemplateListDetail, templateMatchResult,
  templateMatchCandidates, activityTemplateMatchResult, templateListNames,
  activityTraceLabel, activityRouteSummary
} from '@/utils/agentTrace.js';
import ThinkingStatusIcon from '@/components/common/ThinkingStatusIcon.vue';
import TraceTemplateMatch from '@/components/chat/TraceTemplateMatch.vue';

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

const IFRAME_RESIZE_SCRIPT = `(function() {
  function postHeight() {
    try {
      var h = document.documentElement.scrollHeight;
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: 'html-report-resize', height: h }, '*');
      }
    } catch (e) {}
  }
  function observe() {
    postHeight();
    try {
      var ro = window.ResizeObserver;
      if (ro) {
        var observer = new ro(postHeight);
        observer.observe(document.body);
      } else {
        window.addEventListener('resize', postHeight);
      }
    } catch (e) {}
  }
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    observe();
  } else {
    window.addEventListener('load', observe);
  }
})();`;

const HTML_REPORT_MAX_HEIGHT = 1400;
const HTML_REPORT_MIN_HEIGHT = 360;
const PNG_EXPORT_TIMEOUT_MS = 90000;
const pendingPngExports = new Map();
let html2canvasLoader = null;

function installPngSnapshotBridge() {
  let capturing = false;

  function postResult(requestId, payload) {
    window.parent.postMessage({
      type: 'html-report-png-snapshot',
      requestId,
      ...payload
    }, '*');
  }

  function waitForStableLayout() {
    return new Promise((resolve) => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          window.setTimeout(resolve, 700);
        });
      });
    });
  }

  function canvasToImage(canvas, clonedCanvas) {
    const image = document.createElement('img');
    const bounds = canvas.getBoundingClientRect();
    try {
      image.src = canvas.toDataURL('image/png');
    } catch (error) {
      throw new Error(`图表无法转换为图片：${error?.message || error}`);
    }
    image.alt = canvas.getAttribute('aria-label') || '报告图表';
    image.className = clonedCanvas.className || '';
    image.style.cssText = clonedCanvas.style.cssText || '';
    image.style.display = 'block';
    image.style.width = `${Math.max(Math.round(bounds.width), 1)}px`;
    image.style.height = `${Math.max(Math.round(bounds.height), 1)}px`;
    image.setAttribute('width', String(Math.max(Math.round(bounds.width), 1)));
    image.setAttribute('height', String(Math.max(Math.round(bounds.height), 1)));
    if (clonedCanvas.id) image.id = clonedCanvas.id;
    clonedCanvas.replaceWith(image);
  }

  function sanitizeSnapshot(root) {
    root.querySelectorAll(
      'script, noscript, iframe, object, embed, form, base, meta[http-equiv="refresh"]'
    ).forEach((node) => node.remove());
    root.querySelectorAll('*').forEach((element) => {
      for (const attribute of Array.from(element.attributes || [])) {
        const name = attribute.name.toLowerCase();
        if (name.startsWith('on') || name === 'srcdoc') {
          element.removeAttribute(attribute.name);
        }
      }
    });
    const style = document.createElement('style');
    style.textContent = '*,*::before,*::after{animation:none!important;transition:none!important;}';
    (root.querySelector('head') || root).appendChild(style);
  }

  async function createSnapshot(requestId) {
    if (capturing) {
      postResult(requestId, {
        success: false,
        error: 'PNG 报告正在生成，请稍候'
      });
      return;
    }
    capturing = true;
    try {
      if (document.fonts?.ready) {
        await document.fonts.ready;
      }
      await waitForStableLayout();
      const clone = document.documentElement.cloneNode(true);
      const sourceCanvases = Array.from(document.querySelectorAll('canvas'));
      const clonedCanvases = Array.from(clone.querySelectorAll('canvas'));
      sourceCanvases.forEach((canvas, index) => {
        const clonedCanvas = clonedCanvases[index];
        if (clonedCanvas) canvasToImage(canvas, clonedCanvas);
      });
      sanitizeSnapshot(clone);
      postResult(requestId, {
        success: true,
        html: `<!DOCTYPE html>${clone.outerHTML}`
      });
    } catch (error) {
      postResult(requestId, {
        success: false,
        error: error?.message || String(error)
      });
    } finally {
      capturing = false;
    }
  }

  window.addEventListener('message', (event) => {
    const data = event.data;
    if (
      event.source !== window.parent
      || !data
      || data.type !== 'html-report-png-request'
      || !data.requestId
    ) return;
    createSnapshot(data.requestId);
  });
}

function injectResizeScript(doc) {
  let head = doc.querySelector('head');
  if (!head) {
    head = doc.createElement('head');
    const htmlEl = doc.querySelector('html') || doc.documentElement;
    htmlEl.insertBefore(head, htmlEl.firstChild);
  }
  if (head.querySelector('script[data-iframe-resize]')) return;
  const script = doc.createElement('script');
  script.setAttribute('data-iframe-resize', 'true');
  script.textContent = IFRAME_RESIZE_SCRIPT;
  head.appendChild(script);
}

function injectPngSnapshotBridge(doc) {
  let head = doc.querySelector('head');
  if (!head) {
    head = doc.createElement('head');
    const htmlEl = doc.querySelector('html') || doc.documentElement;
    htmlEl.insertBefore(head, htmlEl.firstChild);
  }
  if (!head.querySelector('script[data-png-export-bridge]')) {
    const exportScript = doc.createElement('script');
    exportScript.setAttribute('data-png-export-bridge', 'true');
    exportScript.textContent = `(${installPngSnapshotBridge.toString()})();`;
    head.appendChild(exportScript);
  }
}

function handleHtmlReportResize(event) {
  if (!event.data || event.data.type !== 'html-report-resize') return;
  const height = parseInt(event.data.height, 10);
  if (Number.isNaN(height) || height <= 0) return;
  const iframes = document.querySelectorAll('.html-report-preview');
  for (const iframe of iframes) {
    if (iframe.contentWindow === event.source) {
      const clamped = Math.min(Math.max(height, HTML_REPORT_MIN_HEIGHT), HTML_REPORT_MAX_HEIGHT);
      iframe.style.height = `${clamped}px`;
      break;
    }
  }
}

const chatBody = ref(null);
const fileInputRef = ref(null);
const inputTextareaRef = ref(null);
const inputText = ref('');
const activeConversationId = ref('');
const editingConversationId = ref('');
const renameDraft = ref('');
const uploadedFile = ref(null);
const uploadingFile = ref(false);
const uploadError = ref('');
const draggingFile = ref(false);
const dragDepth = ref(0);
const exportOverlay = ref({ visible: false, label: '' });
let exportOperationId = 0;
let pageUnloading = false;
const sidebarCollapsed = ref(false);
const inputTextareaHeight = ref(24);
const inputResizing = ref(false);
const STORAGE_PREFIX = 'chat_dynamic_messages:';
const RUN_SEQUENCE_PREFIX = 'agent_run_sequence:';
const ACCEPTED_UPLOAD_EXTENSIONS = ['.csv', '.xls', '.xlsx', '.xlsm', '.xltx', '.xltm'];
const INPUT_TEXTAREA_MIN_HEIGHT = 24;
const INPUT_TEXTAREA_MAX_HEIGHT = 180;
const DEFAULT_QUICK_QUESTION_PROMPTS = [
  '帮我生成一份2026年7月“薪运年终奖代发活动”的分析报告',
  '分析一下“薪运年终奖代发活动”并生成报告',
  '基于上传的数据生成活动分析报告'
];
const quickPrompts = ref([...DEFAULT_QUICK_QUESTION_PROMPTS]);

function beginReportExport(label) {
  exportOperationId += 1;
  exportOverlay.value = { visible: true, label };
  return exportOperationId;
}

function handlePngSnapshotResult(event) {
  const data = event.data;
  if (!data || data.type !== 'html-report-png-snapshot' || !data.requestId) return;
  const pending = pendingPngExports.get(data.requestId);
  if (!pending || event.source !== pending.iframe.contentWindow) return;

  window.clearTimeout(pending.timeoutId);
  pendingPngExports.delete(data.requestId);
  if (data.success && typeof data.html === 'string' && data.html) {
    pending.resolve(data.html);
  } else {
    pending.reject(new Error(data.error || '浏览器读取报告快照失败'));
  }
}

function finishReportExport(operationId) {
  if (operationId !== exportOperationId) return;
  exportOverlay.value = { visible: false, label: '' };
}

const {
  userId: urlUserId,
  userName: urlUserName,
  orgNo: urlOrgNo,
  srcSysNo: urlSrcSysNo,
  channel: urlChannel
} = useChatUrlParams();

function createConversation({
  id = `conv-${Date.now()}`,
  title = '新建分析对话',
  meta = '刚刚',
  group = 'today',
  messages = []
} = {}) {
  return {
    id,
    title,
    meta,
    group,
    typing: false,
    dynamicMessages: [...messages]
  };
}

const conversations = ref([]);

const activeConversation = computed(() => (
  conversations.value.find((item) => item.id === activeConversationId.value) || conversations.value[0] || {}
));
const todayConversations = computed(() => conversations.value.filter((item) => item.group === 'today'));
const recentConversations = computed(() => conversations.value.filter((item) => item.group === 'recent'));
const dynamicMessages = computed(() => activeConversation.value?.dynamicMessages || []);
const composerSelectionMessage = computed(() => (
  [...dynamicMessages.value].reverse().find((message) => (
    message.role === 'ai'
    && Array.isArray(message.selectableActivities)
    && (message.selectedIds || []).length > 0
  )) || null
));
const composerSelectedRows = computed(() => (
  composerSelectionMessage.value ? selectedActivityRowNumbers(composerSelectionMessage.value) : []
));
const canSend = computed(() =>
  !hasPendingApproval.value
  && (
    inputText.value.trim().length > 0
    || Boolean(uploadedFile.value?.file_path)
    || composerSelectedRows.value.length > 0
  )
);

const hasPendingApproval = computed(() =>
  activeConversation.value?.dynamicMessages?.some(
    (message) => message.role === 'approval_request' && !message.resolved
  )
);

// 当前运行中 thinking trace 的快照，用于底部浮动进度指示器
const currentRunningTraceSnapshot = computed(() => {
  const conversation = activeConversation.value;
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

function handlePageExit() {
  pageUnloading = true;
}

function handlePageShow() {
  pageUnloading = false;
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

function persistConversation(conversation = activeConversation.value) {
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

function formatMeta(updatedAt) {
  if (!updatedAt) return '刚刚';
  const normalized = /([zZ]|[+-]\d{2}:?\d{2})$/.test(updatedAt)
    ? updatedAt
    : `${updatedAt}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return '刚刚';
  const now = new Date();
  const diff = Math.max(0, now - date);
  if (diff < 60000) return '刚刚';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
  return `${Math.floor(diff / 86400000)}天前`;
}

function calculateGroup(updatedAt) {
  if (!updatedAt) return 'today';
  const normalized = /([zZ]|[+-]\d{2}:?\d{2})$/.test(updatedAt)
    ? updatedAt
    : `${updatedAt}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return 'today';
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const diffDays = Math.floor((now - date) / 86400000);
  if (isToday) return 'today';
  if (diffDays <= 7) return 'recent';
  return 'older';
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

onMounted(async () => {
  pageUnloading = false;
  getUserId();
  window.addEventListener('beforeunload', handlePageExit);
  window.addEventListener('pagehide', handlePageExit);
  window.addEventListener('pageshow', handlePageShow);
  window.addEventListener('message', handleHtmlReportResize);
  window.addEventListener('message', handlePngSnapshotResult);
  try {
    const remotePrompts = await fetchQuickPrompts();
    if (Array.isArray(remotePrompts)) {
      quickPrompts.value = remotePrompts;
    }
  } catch (e) {
    console.warn('加载快捷提问失败，使用默认话术', e);
  }
  try {
    const list = await fetchConversations();
    conversations.value = list.map((c) => ({
      id: c.id,
      title: c.title,
      meta: formatMeta(c.updated_at),
      group: calculateGroup(c.updated_at),
      typing: false,
      // 服务端未返回版本时按 v2 兜底。
      agentVersion: c.agent_version || 'v2',
      dynamicMessages: []
    }));
    if (conversations.value.length > 0) {
      const firstId = conversations.value[0].id;
      activeConversationId.value = firstId;
      await switchConversation(firstId);
    } else {
      // 列表为空时自动创建一个新对话
      await newChat();
    }
  } catch (e) {
    console.error('加载对话列表失败', e);
  }
});

function scrollBottom(conversation = activeConversation.value) {
  if (!conversation || conversation.id !== activeConversationId.value) return;
  nextTick(() => {
    window.setTimeout(() => {
      if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight;
    }, 50);
  });
}

async function newChat() {
  try {
    const data = await createConversationAPI('新建分析对话');
    const next = createConversation({
      id: data.id,
      title: data.title,
      group: 'today',
      meta: '刚刚'
    });
    next.agentVersion = data.agent_version || 'v2';
    conversations.value.unshift(next);
    activeConversationId.value = next.id;
    editingConversationId.value = '';
    renameDraft.value = '';
    inputText.value = '';
    scrollBottom();
  } catch (e) {
    alert('创建对话失败: ' + e.message);
  }
}

async function switchConversation(id) {
  if (editingConversationId.value) {
    const editing = conversations.value.find((item) => item.id === editingConversationId.value);
    if (editing) await saveRename(editing);
  }
  activeConversationId.value = id;
  inputText.value = '';

  const conv = conversations.value.find((c) => c.id === id);
  if (conv && conv.dynamicMessages.length === 0) {
    if (restoreConversationMessages(conv)) {
      try {
        const detail = await fetchConversationMessages(id);
        conv.agentVersion = detail.agentVersion || conv.agentVersion || 'v2';
        addRuntimeTrace(detail.runtimeTrace, conv);
        await restoreConversationReports(detail, conv);
      } catch (e) {
        console.error('恢复报告内容失败', e);
      }
      scrollBottom(conv);
      await recoverAgentRun(conv);
      return;
    }
    try {
      const detail = await fetchConversationMessages(id);
      const messages = Array.isArray(detail) ? detail : detail.messages || [];
      conv.agentVersion = detail.agentVersion || conv.agentVersion || 'v2';
      conv.dynamicMessages = messages.map((m) => {
        if (m.role === 'user') {
          const parsed = parseUserSelectionContent(m.content);
          return { role: 'user', text: parsed.text, selectedRows: parsed.selectedRows };
        }
        return { role: 'ai', text: m.content };
      });
      addRuntimeTrace(detail.runtimeTrace, conv);
      await restoreConversationReports(detail, conv);
    } catch (e) {
      console.error('加载消息历史失败', e);
    }
  }
  if (conv) await recoverAgentRun(conv);
  scrollBottom();
}

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

function startRename(conversation) {
  editingConversationId.value = conversation.id;
  renameDraft.value = conversation.title;
  nextTick(() => {
    document.querySelector('.rename-input')?.focus();
  });
}

async function saveRename(conversation) {
  const nextTitle = renameDraft.value.trim();
  if (!nextTitle) {
    editingConversationId.value = '';
    renameDraft.value = '';
    return;
  }
  try {
    await renameConversationAPI(conversation.id, nextTitle);
    conversation.title = nextTitle;
    editingConversationId.value = '';
    renameDraft.value = '';
  } catch (e) {
    alert('重命名失败: ' + e.message);
  }
}

function cancelRename() {
  editingConversationId.value = '';
  renameDraft.value = '';
}

async function deleteConversation(conversation) {
  const confirmed = window.confirm(`确定删除”${conversation.title}”？`);
  if (!confirmed) return;

  try {
    await deleteConversationAPI(conversation.id);
  } catch (e) {
    alert('删除失败: ' + e.message);
    return;
  }

  const deletedId = conversation.id;
  const deletedIndex = conversations.value.findIndex((item) => item.id === deletedId);
  if (deletedIndex < 0) return;

  conversations.value.splice(deletedIndex, 1);

  if (editingConversationId.value === deletedId) {
    cancelRename();
  }

  if (conversations.value.length === 0) {
    // 全部删除后的替补会话必须注册到服务端——本地 conv-* id 的会话
    // 不会出现在会话列表接口里，刷新页面即丢失（F5 后"会话消失"的根因）
    let replacement = null;
    try {
      const data = await createConversationAPI('新建分析对话 1');
      replacement = createConversation({
        id: data.id,
        title: data.title,
        group: 'today',
        meta: '刚刚'
      });
    } catch (e) {
      console.warn('替补会话注册到服务端失败，退回本地会话', e);
      replacement = createConversation({
        title: '新建分析对话 1',
        group: 'today',
        meta: '刚刚'
      });
    }
    conversations.value.push(replacement);
    activeConversationId.value = replacement.id;
    inputText.value = '';
    scrollBottom();
    return;
  }

  if (activeConversationId.value === deletedId) {
    const nextConversation = conversations.value[deletedIndex] || conversations.value[deletedIndex - 1] || conversations.value[0];
    activeConversationId.value = nextConversation.id;
    inputText.value = '';
    scrollBottom();
  }
}

function addMessage(role, text, conversation = activeConversation.value, metadata = {}) {
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
  scrollBottom(conversation);
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

function addHtmlReport(html, conversation = activeConversation.value, payload = {}, insertIndex = null) {
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
    scrollBottom(conversation);
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
  scrollBottom(conversation);
}

function hasRunningThinking(conversation = activeConversation.value) {
  return Boolean(conversation?.dynamicMessages?.some((message) => (
    message.role === 'execution_trace' && message.status === 'running'
  )));
}

function scrollToRunningTrace() {
  const conversation = activeConversation.value;
  const trace = conversation?.dynamicMessages?.find((message) => (
    message.role === 'execution_trace' && message.status === 'running'
  ));
  if (!trace || !chatBody.value) return;
  const index = conversation.dynamicMessages.indexOf(trace);
  if (index < 0) return;
  nextTick(() => {
    const target = chatBody.value.querySelector(`.trace-row[data-trace-index="${index}"]`);
    if (!target) return;
    const top = target.offsetTop - 80;
    chatBody.value.scrollTo({ top, behavior: 'smooth' });
  });
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

function resumePausedThinkingTrace(conversation = activeConversation.value) {
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

function hasActivityFetchStep(message) {
  return Array.isArray(message?.steps) && message.steps.some((step) => (
    stepKey(step) === 'marketing_data_fetch' && step.payload?.activity_list
  ));
}

function finishRunningThinking(conversation = activeConversation.value, payload = {}) {
  const trace = conversation?.dynamicMessages?.find((message) => (
    message.role === 'execution_trace' && message.status === 'running'
  ));
  finishThinkingTrace(trace, payload);
}

function addRuntimeTrace(runtimeTrace, conversation = activeConversation.value) {
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

// 剥离历史报告中"数据来源：…"一类的页脚尾注（新生成的报告已由后端清理，
// 这里兜底处理库存量报告）。
function stripReportFooterNote(html) {
  if (!html) return html;
  return html
    .replace(/\s*<(p|div|footer|section|span)\b[^>]*>\s*(?:报告生成时间[:：][^<\n\r]*)?数据来源[:：][^<\n\r]*\s*<\/\1>\s*/gi, '')
    .replace(/^[ \t]*(?:报告生成时间[:：][^<\n\r]*)?数据来源[:：][^<\n\r]*[ \t]*\r?\n?/gim, '')
    .replace(/\s*<(p|div|footer|section|span)\b[^>]*>\s*报告基于[^<\n\r]*?生成[^<\n\r]*\s*<\/\1>\s*/gi, '')
    .replace(/^[ \t]*报告基于[^<\n\r]*?生成[^<\n\r]*[ \t]*\r?\n?/gim, '');
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

function pruneEmptyCompletedTraces(conversation = activeConversation.value) {
  if (!Array.isArray(conversation?.dynamicMessages)) return;
  conversation.dynamicMessages = conversation.dynamicMessages.filter((message) => (
    message?.role !== 'execution_trace' || shouldDisplayThinkingTrace(message)
  ));
}

function attachActivitySelection(message, activities, conversation = activeConversation.value) {
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
  scrollBottom(conversation);
}

function toggleActivitySelection(message, activity) {
  toggleActivitySelectionPure(message, activity);
  persistConversation();
}

function setAllActivityRows(message, checked) {
  // 批量选择某张表时，清空其他查询表的草稿选择，避免行号来源混淆。
  for (const item of activeConversation.value?.dynamicMessages || []) {
    if (item !== message && item.role === 'ai' && Array.isArray(item.selectableActivities)) {
      item.selectedIds = [];
    }
  }
  message.selectedIds = checked
    ? selectionActivities(message).map((activity) => activityId(activity)).filter(Boolean)
    : [];
  persistConversation();
  nextTick(() => inputTextareaRef.value?.focus());
}

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

  // 输入区只引用一份查询结果；选择旧/新表格时清空其他表格的草稿选择。
  for (const item of activeConversation.value?.dynamicMessages || []) {
    if (item !== message && item.role === 'ai' && Array.isArray(item.selectableActivities)) {
      item.selectedIds = [];
    }
  }
  toggleActivitySelection(message, activity);
  nextTick(() => inputTextareaRef.value?.focus());
}

function removeComposerSelectedRow(rowNumber) {
  const message = composerSelectionMessage.value;
  if (!message) return;
  const activity = selectionActivities(message).find(
    (item, index) => activityRowNumber(item, index) === rowNumber
  );
  if (activity) toggleActivitySelection(message, activity);
}

function addApprovalRequest(payload, conversation = activeConversation.value) {
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
  scrollBottom(conversation);
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

async function resolveApproval(message, decision, editedArgs = null) {
  if (message.resolved) return;
  const conversation = activeConversation.value;
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
      userId: urlUserId || getUserId(),
      userName: urlUserName,
      orgNo: urlOrgNo,
      srcSysNo: urlSrcSysNo,
      channel: urlChannel
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

function triggerFileUpload() {
  if (activeConversation.value?.typing || uploadingFile.value) return;
  uploadError.value = '';
  fileInputRef.value?.click();
}

function canUploadNow() {
  return !activeConversation.value?.typing && !uploadingFile.value;
}

function isDragWithFiles(event) {
  return Array.from(event.dataTransfer?.types || []).includes('Files');
}

function validateUploadFile(file) {
  const lowerName = (file?.name || '').toLowerCase();
  return ACCEPTED_UPLOAD_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
}

async function uploadSelectedFile(file) {
  if (!file || !canUploadNow()) return;
  if (!validateUploadFile(file)) {
    uploadedFile.value = null;
    uploadError.value = `仅支持 ${ACCEPTED_UPLOAD_EXTENSIONS.join('、')} 文件`;
    return;
  }

  uploadingFile.value = true;
  uploadError.value = '';
  try {
    uploadedFile.value = await uploadFile(file);
    if (!inputText.value.trim()) {
      inputText.value = `请基于上传的活动数据文件「${uploadedFile.value.file_name}」生成分析报告`;
    }
  } catch (e) {
    uploadedFile.value = null;
    uploadError.value = e.message || '文件上传失败';
  } finally {
    uploadingFile.value = false;
  }
}

async function handleFileSelected(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  await uploadSelectedFile(file);
}

function handleFileDragEnter(event) {
  if (!isDragWithFiles(event)) return;
  dragDepth.value += 1;
  if (canUploadNow()) {
    draggingFile.value = true;
    event.dataTransfer.dropEffect = 'copy';
  }
}

function handleFileDragOver(event) {
  if (!isDragWithFiles(event)) return;
  event.dataTransfer.dropEffect = canUploadNow() ? 'copy' : 'none';
}

function handleFileDragLeave(event) {
  if (!isDragWithFiles(event)) return;
  dragDepth.value = Math.max(0, dragDepth.value - 1);
  if (dragDepth.value === 0) {
    draggingFile.value = false;
  }
}

async function handleFileDrop(event) {
  if (!isDragWithFiles(event)) return;
  dragDepth.value = 0;
  draggingFile.value = false;
  const file = event.dataTransfer?.files?.[0];
  await uploadSelectedFile(file);
}

function removeUploadedFile() {
  if (activeConversation.value?.typing || uploadingFile.value) return;
  uploadedFile.value = null;
  uploadError.value = '';
}

function buildHtmlDocument(message) {
  let html = (message.html || '').trim();
  if (!html) return '';
  // 兜底：去除 LLM 可能附带的前言文字，只保留从 HTML 标签开始的内容
  const htmlStartMatch = html.match(/<(html|!doctype|section|div|body|head|main|article)/i);
  if (htmlStartMatch && htmlStartMatch.index > 0) {
    html = html.slice(htmlStartMatch.index);
  }
  // 统一将 LLM 可能使用的任意 ECharts CDN 或路径替换为项目本地路径
  html = html.replace(
    /https?:\/\/[^"'\s]*echarts[^"'\s]*\.min\.js/gi,
    '/lib/echarts.min.js'
  );

  // 使用 DOMParser 做结构化兜底：确保 echarts 库在 head 中同步加载，并修复裸 option 对象
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const ECHARTS_SRC = '/lib/echarts.min.js';

    // 规范化已有的 echarts 脚本引用。
    const scripts = Array.from(doc.querySelectorAll('script'));
    const echartsScripts = scripts.filter((s) => {
      const src = s.getAttribute('src') || '';
      return /echarts/i.test(src) && /\.min\.js$/i.test(src);
    });
    echartsScripts.forEach((s) => {
      s.setAttribute('src', ECHARTS_SRC);
      s.removeAttribute('async');
      s.removeAttribute('defer');
      if (s.getAttribute('type') === 'text/javascript') s.removeAttribute('type');
    });

    // 确保 head 中存在唯一一个 echarts 同步脚本。
    let head = doc.querySelector('head');
    if (!head) {
      head = doc.createElement('head');
      const htmlEl = doc.querySelector('html') || doc.documentElement;
      htmlEl.insertBefore(head, htmlEl.firstChild);
    }
    if (echartsScripts.length === 0) {
      const script = doc.createElement('script');
      script.setAttribute('src', ECHARTS_SRC);
      head.appendChild(script);
    } else {
      // 只保留第一个，移动到 head，其余删除。
      const first = echartsScripts[0];
      echartsScripts.slice(1).forEach((s) => s.remove());
      head.appendChild(first);
    }

    // 兜底修复裸 ECharts option 对象字面量：将 { ... } 包装成 IIFE。
    scripts.forEach((script) => {
      const content = script.textContent || '';
      const trimmed = content.trim();
      if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return;
      // 简单校验：是单一顶层对象字面量
      let depth = 0;
      let inString = false;
      let stringChar = null;
      let escaped = false;
      let isSingleObject = true;
      for (let i = 0; i < trimmed.length; i += 1) {
        const ch = trimmed[i];
        if (escaped) {
          escaped = false;
          continue;
        }
        if (ch === '\\') {
          escaped = true;
          continue;
        }
        if (inString) {
          if (ch === stringChar) inString = false;
          continue;
        }
        if (ch === '"' || ch === "'") {
          inString = true;
          stringChar = ch;
          continue;
        }
        if (ch === '{') depth += 1;
        else if (ch === '}') {
          depth -= 1;
          if (depth === 0 && i !== trimmed.length - 1) {
            isSingleObject = false;
            break;
          }
        }
      }
      if (!isSingleObject || depth !== 0 || inString) return;

      // 寻找最近的 chart 容器
      let chartId = null;
      let el = script.previousElementSibling;
      while (el && !chartId) {
        const id = el.getAttribute('id') || '';
        if (id.toLowerCase().startsWith('chart')) chartId = id;
        el = el.previousElementSibling;
      }
      if (!chartId) {
        const allCharts = Array.from(doc.querySelectorAll('[id^="chart-"], [id^="chart_"], [id^="chartA"], [id^="chartB"], [id^="chartC"], [id^="chartD"], [id^="chartE"], [id^="chartF"], [id^="chartG"], [id^="chartH"], [id^="chartI"], [id^="chartJ"], [id^="chartK"], [id^="chartL"], [id^="chartM"], [id^="chartN"], [id^="chartO"], [id^="chartP"], [id^="chartQ"], [id^="chartR"], [id^="chartS"], [id^="chartT"], [id^="chartU"], [id^="chartV"], [id^="chartW"], [id^="chartX"], [id^="chartY"], [id^="chartZ"], [id^="chart0"], [id^="chart1"], [id^="chart2"], [id^="chart3"], [id^="chart4"], [id^="chart5"], [id^="chart6"], [id^="chart7"], [id^="chart8"], [id^="chart9"]'));
        const scriptIndex = scripts.indexOf(script);
        const precedingCharts = allCharts.filter((c) => {
          const containers = Array.from(doc.querySelectorAll('div'));
          return containers.indexOf(c) < containers.indexOf(script);
        });
        chartId = precedingCharts[precedingCharts.length - 1]?.getAttribute('id');
      }
      if (!chartId) return;

      script.textContent = `(function() {\n  var chartDom = document.getElementById('${chartId}');\n  if (!chartDom) return;\n  var myChart = echarts.init(chartDom);\n  var option = ${trimmed};\n  myChart.setOption(option);\n  window.addEventListener('resize', function() { myChart.resize(); });\n})();`;
    });

    // 注入 iframe 高度自适应脚本，让预览 iframe 根据报告内容自动调整高度
    injectResizeScript(doc);
    // 沙箱 iframe 只回传无脚本静态快照，PNG 在父页面的同源环境生成。
    injectPngSnapshotBridge(doc);

    // 使用 outerHTML 做 HTML 序列化（而非 XMLSerializer），避免 <script> 中的 < > & 被转义为 XML 实体，
    // 否则浏览器会以 HTML 模式重新解析时不会解码 &lt; / &gt;，导致 JS 报 "lt is not defined" 等语法错误。
    const doctype = doc.doctype ? `<!DOCTYPE ${doc.doctype.name}>` : '';
    html = doctype + doc.documentElement.outerHTML;
  } catch (e) {
    console.warn('HTML 报告结构化兜底处理失败，使用原始 HTML', e);
  }

  const scriptOpen = '<' + 'script data-iframe-resize="true">';
  const scriptClose = '<' + '/script>';
  const pngBridgeScriptOpen = '<' + 'script data-png-export-bridge="true">';
  const escapedResizeScript = IFRAME_RESIZE_SCRIPT.replace(/<\/script/gi, '<\\/script');
  const escapedPngBridgeScript = `(${installPngSnapshotBridge.toString()})();`
    .replace(/<\/script/gi, '<\\/script');
  return html.toLowerCase().startsWith('<!doctype') || html.toLowerCase().startsWith('<html')
    ? html
    : `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${message.title || '活动分析报告'}</title>
  ${scriptOpen}${escapedResizeScript}${scriptClose}
  ${pngBridgeScriptOpen}${escapedPngBridgeScript}${scriptClose}
  <style>
    body { margin: 0; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color: #1f2937; line-height: 1.65; background: #fff; }
    h1, h2, h3 { color: #111827; line-height: 1.35; }
    h1 { font-size: 26px; margin: 0 0 16px; }
    h2 { font-size: 20px; margin: 24px 0 12px; }
    h3 { font-size: 16px; margin: 18px 0 10px; }
    p, li { font-size: 14px; color: #475569; }
    table { width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 13px; }
    th, td { border: 1px solid #e5e7eb; padding: 9px 10px; text-align: left; }
    th { background: #f8fafc; color: #334155; }
    pre { white-space: pre-wrap; word-break: break-word; background: #f8fafc; border-radius: 8px; padding: 12px; font-size: 12px; color: #334155; }
  </style>
</head>
<body>
${html}
</body>
</html>`;
}

async function downloadHtmlReport(message) {
  const html = (message.html || '').trim();
  if (!html) return;
  const operationId = beginReportExport('正在导出 HTML 报告…');

  try {
    const response = await fetch(`${API_BASE}/reports/html`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        html,
        title: message.title || '活动分析报告'
      })
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${response.status}`);
    }
    const htmlBlob = await response.blob();
    const url = URL.createObjectURL(htmlBlob);
    const link = document.createElement('a');
    const date = new Date().toISOString().slice(0, 10);
    link.href = url;
    link.download = `活动分析报告-${date}.html`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error('下载HTML报告失败', e);
    alert('下载HTML报告失败：' + e.message);
  } finally {
    finishReportExport(operationId);
  }
}

function safeDownloadName(value, fallback = '活动分析报告') {
  return String(value || fallback)
    .replace(/[\\/:*?"<>|\r\n]+/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80) || fallback;
}

function requestPngSnapshot(iframe) {
  return new Promise((resolve, reject) => {
    if (!iframe?.contentWindow) {
      reject(new Error('没有找到当前报告预览，请刷新页面后重试'));
      return;
    }
    const requestId = `png-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const timeoutId = window.setTimeout(() => {
      pendingPngExports.delete(requestId);
      reject(new Error('读取报告快照超时，请刷新页面后重试'));
    }, 15000);
    pendingPngExports.set(requestId, { iframe, timeoutId, resolve, reject });
    iframe.contentWindow.postMessage({
      type: 'html-report-png-request',
      requestId
    }, '*');
  });
}

function sanitizePngSnapshotHtml(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  doc.querySelectorAll(
    'script, noscript, iframe, object, embed, form, base, meta[http-equiv="refresh"]'
  ).forEach((node) => node.remove());
  doc.querySelectorAll('*').forEach((element) => {
    for (const attribute of Array.from(element.attributes || [])) {
      const name = attribute.name.toLowerCase();
      if (name.startsWith('on') || name === 'srcdoc') {
        element.removeAttribute(attribute.name);
      }
    }
  });
  return `<!DOCTYPE html>${doc.documentElement.outerHTML}`;
}

function waitForStaticFrame(iframe) {
  return new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(
      () => reject(new Error('静态报告渲染超时')),
      15000
    );
    iframe.addEventListener('load', () => {
      window.clearTimeout(timeoutId);
      resolve();
    }, { once: true });
    iframe.addEventListener('error', () => {
      window.clearTimeout(timeoutId);
      reject(new Error('静态报告加载失败'));
    }, { once: true });
  });
}

async function waitForSnapshotAssets(doc) {
  if (doc.fonts?.ready) {
    await doc.fonts.ready;
  }
  const images = Array.from(doc.images || []);
  await Promise.all(images.map((image) => {
    if (image.complete) return Promise.resolve();
    return new Promise((resolve) => {
      image.addEventListener('load', resolve, { once: true });
      image.addEventListener('error', resolve, { once: true });
    });
  }));
  await new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });
}

function pngRenderScale(width, height) {
  const maxDimension = 16000;
  const maxPixels = 36000000;
  const scale = Math.min(
    2,
    maxDimension / width,
    maxDimension / height,
    Math.sqrt(maxPixels / (width * height))
  );
  if (!Number.isFinite(scale) || scale < 0.35) {
    throw new Error('报告内容过长，当前浏览器无法生成清晰的单张 PNG，请下载 HTML 报告');
  }
  return scale;
}

async function renderSnapshotToPng(snapshotHtml, viewportWidth) {
  if (!html2canvasLoader) {
    html2canvasLoader = import('html2canvas').then((module) => module.default);
  }
  const iframe = document.createElement('iframe');
  // 静态快照允许父页面同源读取，但禁止执行任何脚本。
  iframe.setAttribute('sandbox', 'allow-same-origin');
  iframe.setAttribute('aria-hidden', 'true');
  iframe.tabIndex = -1;
  Object.assign(iframe.style, {
    position: 'fixed',
    left: '-100000px',
    top: '0',
    width: `${Math.max(Math.round(viewportWidth || 0), 800)}px`,
    height: '900px',
    border: '0',
    pointerEvents: 'none'
  });

  const loaded = waitForStaticFrame(iframe);
  iframe.srcdoc = sanitizePngSnapshotHtml(snapshotHtml);
  document.body.appendChild(iframe);
  try {
    const [html2canvas] = await Promise.all([html2canvasLoader, loaded]);
    const doc = iframe.contentDocument;
    if (!doc?.body) throw new Error('无法读取静态报告内容');
    await waitForSnapshotAssets(doc);

    const body = doc.body;
    const root = doc.documentElement;
    const width = Math.max(
      body.scrollWidth,
      body.offsetWidth,
      root.scrollWidth,
      root.offsetWidth,
      1
    );
    const height = Math.max(
      body.scrollHeight,
      body.offsetHeight,
      root.scrollHeight,
      root.offsetHeight,
      1
    );
    const scale = pngRenderScale(width, height);
    const canvas = await Promise.race([
      html2canvas(body, {
        backgroundColor: '#ffffff',
        scale,
        useCORS: true,
        allowTaint: false,
        logging: false,
        scrollX: 0,
        scrollY: 0,
        width,
        height,
        windowWidth: width,
        windowHeight: height
      }),
      new Promise((_, reject) => {
        window.setTimeout(
          () => reject(new Error('PNG 生成超时，请稍后重试或下载 HTML 报告')),
          PNG_EXPORT_TIMEOUT_MS
        );
      })
    ]);
    return await new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => blob
          ? resolve(blob)
          : reject(new Error('浏览器生成 PNG 文件失败')),
        'image/png'
      );
    });
  } finally {
    iframe.remove();
  }
}

async function downloadPngReport(message, event) {
  const operationId = beginReportExport('正在使用当前浏览器生成 PNG 报告…');
  try {
    const reportCard = event?.currentTarget?.closest('.html-report-card');
    const reportIframe = reportCard?.querySelector('.html-report-preview');
    const snapshotHtml = await requestPngSnapshot(reportIframe);
    const blob = await renderSnapshotToPng(
      snapshotHtml,
      reportIframe?.clientWidth
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const date = new Date().toISOString().slice(0, 10);
    link.href = url;
    link.download = `${safeDownloadName(message.title)}-${date}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error('下载PNG报告失败', error);
    alert(`下载PNG报告失败：${error.message || error}`);
  } finally {
    finishReportExport(operationId);
  }
}

function escapeHtmlText(value) {
  return String(value || '').replace(/[<>&"]/g, (ch) => ({
    '<': '&lt;',
    '>': '&gt;',
    '&': '&amp;',
    '"': '&quot;'
  }[ch]));
}

async function openHtmlReportInNewTab(message) {
  const reportWindow = window.open('', '_blank');
  if (!reportWindow) {
    alert('无法打开新页签，请允许浏览器弹出窗口后重试');
    return;
  }
  reportWindow.opener = null;
  reportWindow.document.open();
  reportWindow.document.write(`<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>${escapeHtmlText(message.title || '活动分析报告')}</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color: #475569; background: #f8fafc; }
  </style>
</head>
<body>正在打开报告...</body>
</html>`);
  reportWindow.document.close();

  try {
    let documentHtml = buildHtmlDocument(message);
    if (!documentHtml) return;
    documentHtml = await inlineEchartsScript(documentHtml);
    reportWindow.document.open();
    reportWindow.document.write(documentHtml);
    reportWindow.document.close();
    reportWindow.focus();
  } catch (e) {
    console.error('新页签打开HTML报告失败', e);
    const errorMessage = escapeHtmlText(e.message || e);
    reportWindow.document.open();
    reportWindow.document.write(`<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>报告打开失败</title>
  <style>
    body { margin: 0; padding: 32px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color: #1f2937; background: #fff; }
    .error { max-width: 720px; margin: 0 auto; padding: 18px 20px; border: 1px solid #fecdd3; border-radius: 8px; background: #fff1f2; color: #b42318; }
  </style>
</head>
<body><div class="error">打开报告失败：${errorMessage}</div></body>
</html>`);
    reportWindow.document.close();
  }
}

async function inlineEchartsScript(html) {
  const response = await fetch('/lib/echarts.min.js');
  if (!response.ok) throw new Error('无法加载 echarts.min.js');
  const echartsScript = await response.text();

  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const scripts = Array.from(doc.querySelectorAll('script'));
    const echartsScripts = scripts.filter((script) => {
      const src = script.getAttribute('src') || '';
      return /echarts/i.test(src) && /\.js(\?.*)?$/i.test(src);
    });
    const inlineScript = doc.createElement('script');
    inlineScript.textContent = `\n${echartsScript}\n`;

    if (echartsScripts.length > 0) {
      echartsScripts[0].replaceWith(inlineScript);
      echartsScripts.slice(1).forEach((script) => script.remove());
    } else {
      const head = doc.querySelector('head') || doc.documentElement;
      head.appendChild(inlineScript);
    }

    const doctype = doc.doctype ? `<!DOCTYPE ${doc.doctype.name}>` : '<!doctype html>';
    return `${doctype}${doc.documentElement.outerHTML}`;
  } catch (e) {
    console.warn('内联 ECharts 失败，使用字符串替换兜底', e);
    const openingScript = '<' + 'script>';
    const closingScript = '<' + '/script>';
    const escapedScript = `${openingScript}\n${echartsScript.replace(new RegExp(closingScript, 'gi'), '<\\/script')}\n${closingScript}`;
    const echartsSrcPattern = new RegExp(
      '<' + 'script[^>]+src=["\'][^"\']*echarts[^"\']*["\'][^>]*>\\s*<' + '\\/script>',
      'i'
    );
    if (echartsSrcPattern.test(html)) {
      return html.replace(echartsSrcPattern, escapedScript);
    }
    const headClosePattern = new RegExp('<' + '\\/head\\s*>', 'i');
    if (headClosePattern.test(html)) {
      return html.replace(headClosePattern, `${escapedScript}</head>`);
    }
    return `${escapedScript}\n${html}`;
  }
}

async function submitReportFeedbackToServer(message, feedback, comment) {
  const threadId = activeConversation.value?.id || '';
  message.feedbackSaving = true;
  message.feedbackError = '';
  try {
    const options = {};
    if (message.versionNo !== undefined && message.versionNo !== null) {
      options.versionNo = message.versionNo;
    }
    if (comment) {
      options.comment = comment;
    }
    const saved = await submitReportFeedback(message.reportRequestId || message.requestId, feedback, threadId, options);
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
  const threadId = activeConversation.value?.id || '';
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
  return Boolean(message?.requestId || activeConversation.value?.id);
}

async function reconnectAgentStream(conversation, options = {}) {
  if (pageUnloading || (options.reconnectAttempts || 0) >= 2) return pageUnloading;
  try {
    const after = getRunSequence(conversation.id);
    const status = await getAgentV2RunStatus(conversation.id);
    if (!status?.exists || (!status.active && Number(status.last_seq || 0) <= after)) {
      return false;
    }
    const response = await attachAgentV2Run(conversation.id, after);
    if (!response.ok) return false;
    await consumeAgentStream(response, conversation, {
      ...options,
      recovery: true,
      reconnectAttempts: (options.reconnectAttempts || 0) + 1
    });
    return true;
  } catch (e) {
    console.warn('任务流自动续接失败', e);
    return false;
  }
}

async function consumeAgentStream(response, conversation, options = {}) {
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
            scrollBottom();
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

            const replyAlreadyRestored = options.recovery && conversation.dynamicMessages.some(
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
    if (await reconnectAgentStream(conversation, options)) return;
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
    if (isTransportError(e) && await reconnectAgentStream(conversation, options)) return;
    conversation.typing = false;
    finishRunningThinking(conversation);
    const errorMessage = requestErrorMessage(e);
    addMessage('ai', errorMessage, conversation, {
      transportFallback: errorMessage === SYSTEM_BUSY_MESSAGE
    });
  }
}

async function sendMsg() {
  const text = inputText.value.trim();
  const currentUploadedFile = uploadedFile.value;
  const selectedRows = [...composerSelectedRows.value];
  if (!text && !currentUploadedFile?.file_path && selectedRows.length === 0) return;
  const selectionText = selectedRows.length
    ? `已选择第 ${selectedRows.join('、')} 行`
    : '';
  const personalRequestText = text || (
    currentUploadedFile?.file_name
      ? `请基于上传的活动数据文件「${currentUploadedFile.file_name}」生成分析报告`
      : ''
  );
  const requestText = [selectionText, personalRequestText].filter(Boolean).join('\n');

  const conversation = activeConversation.value;

  // 历史遗留的本地 conv-* 会话（如旧版删除全部会话后的替补会话）未在服务端
  // 注册，直接发送会导致刷新后会话丢失。发送前先注册到服务端并迁移 id；
  // 后端图上下文从本条消息重新开始（UI 消息记录保留）。
  if (conversation.id?.startsWith('conv-')) {
    try {
      const data = await createConversationAPI(conversation.title || '新建分析对话');
      const oldId = conversation.id;
      conversation.id = data.id;
      if (activeConversationId.value === oldId) {
        activeConversationId.value = data.id;
      }
      const cached = localStorage.getItem(storageKey(oldId));
      if (cached) {
        localStorage.setItem(storageKey(data.id), cached);
        localStorage.removeItem(storageKey(oldId));
      }
    } catch (e) {
      console.warn('本地会话注册到服务端失败，继续使用本地会话', e);
    }
  }

  if (conversation.typing) return;
  inputText.value = '';
  uploadedFile.value = null;
  uploadError.value = '';

  // 本地添加用户消息（addMessage 会自动生成标题）
  const displayText = currentUploadedFile?.file_name
    ? `${personalRequestText}\n\n附件：${currentUploadedFile.file_name}`
    : personalRequestText;
  addMessage('user', displayText, conversation, { selectedRows });
  if (composerSelectionMessage.value) {
    composerSelectionMessage.value.selectedIds = [];
    persistConversation(conversation);
  }

  // 如果是第一条用户消息，同步标题到后端
  const isFirstUserMessage = conversation.dynamicMessages.filter((m) => m.role === 'user').length === 1;
  if (isFirstUserMessage && conversation.title) {
    try {
      await renameConversationAPI(conversation.id, conversation.title);
    } catch (e) {
      console.error('同步标题失败', e);
    }
  }

  // 调用后端 SSE /api/v2/agent/run
  conversation.typing = true;
  setRunSequence(conversation.id, 0);
  scrollBottom();

  // 新请求开始时，若存在前一次异常中断残留的 running trace，先将其关闭
  const staleRunningTrace = conversation.dynamicMessages.find((message) => (
    message.role === 'execution_trace' && message.status === 'running'
  ));
  if (staleRunningTrace) {
    finishThinkingTrace(staleRunningTrace, { message: '前一次任务已中断' });
  }

  try {
    const userId = getUserId();
    const response = await runAgentV2({
      threadId: conversation.id,
      message: requestText,
      // originalUserText 是“本轮”用户消息的展示文本（刷新后按它重建气泡），
      // 必须随轮次变化；曾误用 originalUserQuestion（恒为会话第一个问题），
      // 导致刷新后每轮用户气泡都显示成第一个问题。
      originalUserText: displayText || requestText,
      filePath: currentUploadedFile?.file_path || '',
      userId: urlUserId || getUserId(),
      userName: urlUserName,
      orgNo: urlOrgNo,
      srcSysNo: urlSrcSysNo,
      channel: urlChannel
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

async function cancelRun() {
  const conversation = activeConversation.value;
  if (!conversation || !conversation.typing) return;

  try {
    await cancelAgentV2(conversation.id);
  } catch (e) {
    console.error('取消请求失败', e);
  }
}

function handleKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMsg();
  }
}

async function useQuickQuestionPrompt(prompt) {
  inputText.value = prompt;
  await nextTick();
  inputTextareaRef.value?.focus();
}

let inputResizeStartY = 0;
let inputResizeStartHeight = 0;

function clampInputTextareaHeight(value) {
  return Math.min(INPUT_TEXTAREA_MAX_HEIGHT, Math.max(INPUT_TEXTAREA_MIN_HEIGHT, value));
}

function handleInputResizeMove(event) {
  if (!inputResizing.value) return;
  const delta = inputResizeStartY - event.clientY;
  inputTextareaHeight.value = clampInputTextareaHeight(inputResizeStartHeight + delta);
}

function stopInputResize() {
  if (!inputResizing.value) return;
  inputResizing.value = false;
  window.removeEventListener('pointermove', handleInputResizeMove);
  window.removeEventListener('pointerup', stopInputResize);
}

function startInputResize(event) {
  if (event.button !== undefined && event.button !== 0) return;
  inputResizing.value = true;
  inputResizeStartY = event.clientY;
  inputResizeStartHeight = inputTextareaHeight.value;
  window.addEventListener('pointermove', handleInputResizeMove);
  window.addEventListener('pointerup', stopInputResize);
  event.preventDefault();
}

onBeforeUnmount(() => {
  pageUnloading = true;
  stopInputResize();
  window.removeEventListener('beforeunload', handlePageExit);
  window.removeEventListener('pagehide', handlePageExit);
  window.removeEventListener('pageshow', handlePageShow);
  window.removeEventListener('message', handleHtmlReportResize);
  window.removeEventListener('message', handlePngSnapshotResult);
  for (const pending of pendingPngExports.values()) {
    window.clearTimeout(pending.timeoutId);
    pending.reject(new Error('页面已关闭，PNG 导出已取消'));
  }
  pendingPngExports.clear();
});
</script>

<template>
  <div class="ui-chat-page">
    <div class="shell">
      <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
        <div class="sb-head">
          <div class="sb-top">
            <div class="sb-logo">
              <div class="sb-logo-ic"><i class="ti ti-chart-dots-3" aria-hidden="true"></i></div>
              <div class="sb-logo-text">
                <div class="sb-logo-name">活动分析助手</div>
                <div class="sb-logo-sub">对话式报告生成</div>
              </div>
            </div>
            <button
              class="collapse-btn"
              type="button"
              :title="sidebarCollapsed ? '展开边栏' : '收起边栏'"
              :aria-label="sidebarCollapsed ? '展开边栏' : '收起边栏'"
              @click="sidebarCollapsed = !sidebarCollapsed"
            >
              <i :class="sidebarCollapsed ? 'ti ti-layout-sidebar-left-expand' : 'ti ti-layout-sidebar-left-collapse'" aria-hidden="true"></i>
            </button>
          </div>
          <button class="new-btn" type="button" title="新建分析对话" @click="newChat">
            <i class="ti ti-circle-plus" aria-hidden="true"></i>
            <span>新建分析对话</span>
          </button>
        </div>
        <div class="sb-body">
          <div class="sb-section">今天</div>
          <div
            v-for="conversation in todayConversations"
            :key="conversation.id"
            class="sb-item"
            :class="{ active: conversation.id === activeConversation.id }"
            role="button"
            tabindex="0"
            @click="switchConversation(conversation.id)"
            @keydown.enter.prevent="switchConversation(conversation.id)"
            @keydown.space.prevent="switchConversation(conversation.id)"
          >
            <i class="ti ti-message-circle" aria-hidden="true"></i>
            <input
              v-if="editingConversationId === conversation.id"
              v-model="renameDraft"
              class="rename-input"
              @blur="saveRename(conversation)"
              @click.stop
              @keydown.enter.stop.prevent="saveRename(conversation)"
              @keydown.esc.stop.prevent="cancelRename"
            >
            <span v-else class="sb-title">{{ conversation.title }}</span>
            <button
              v-if="editingConversationId !== conversation.id"
              class="rename-btn"
              type="button"
              title="重命名"
              aria-label="重命名对话"
              @click.stop="startRename(conversation)"
            >
              <i class="ti ti-pencil" aria-hidden="true"></i>
            </button>
            <button
              v-if="editingConversationId !== conversation.id"
              class="delete-btn"
              type="button"
              title="删除"
              aria-label="删除对话"
              @click.stop="deleteConversation(conversation)"
            >
              <i class="ti ti-trash" aria-hidden="true"></i>
            </button>
            <span class="sb-meta">{{ conversation.meta }}</span>
          </div>
          <div class="sb-section">最近7天</div>
          <div
            v-for="conversation in recentConversations"
            :key="conversation.id"
            class="sb-item"
            :class="{ active: conversation.id === activeConversation.id }"
            role="button"
            tabindex="0"
            @click="switchConversation(conversation.id)"
            @keydown.enter.prevent="switchConversation(conversation.id)"
            @keydown.space.prevent="switchConversation(conversation.id)"
          >
            <i class="ti ti-message-circle" aria-hidden="true"></i>
            <input
              v-if="editingConversationId === conversation.id"
              v-model="renameDraft"
              class="rename-input"
              @blur="saveRename(conversation)"
              @click.stop
              @keydown.enter.stop.prevent="saveRename(conversation)"
              @keydown.esc.stop.prevent="cancelRename"
            >
            <span v-else class="sb-title">{{ conversation.title }}</span>
            <button
              v-if="editingConversationId !== conversation.id"
              class="rename-btn"
              type="button"
              title="重命名"
              aria-label="重命名对话"
              @click.stop="startRename(conversation)"
            >
              <i class="ti ti-pencil" aria-hidden="true"></i>
            </button>
            <button
              v-if="editingConversationId !== conversation.id"
              class="delete-btn"
              type="button"
              title="删除"
              aria-label="删除对话"
              @click.stop="deleteConversation(conversation)"
            >
              <i class="ti ti-trash" aria-hidden="true"></i>
            </button>
            <span class="sb-meta">{{ conversation.meta }}</span>
          </div>
        </div>
      </aside>

      <main class="main">
        <header class="chat-head">
          <div class="head-icon"><i class="ti ti-chart-dots-3" aria-hidden="true"></i></div>
          <div>
            <div class="chat-head-title">活动分析助手</div>
            <div class="chat-head-sub">对话驱动 · 智能匹配 · 一键生成报告</div>
          </div>
          <div class="chat-head-badges">
            <span class="cbadge cbadge-green"><i class="ti ti-circle-check" aria-hidden="true"></i>已就绪</span>
          </div>
        </header>

        <section ref="chatBody" class="chat-body">
          <div class="divider-msg">新对话开始</div>

          <div class="msg-row">
            <div class="avatar av-ai"><i class="ti ti-sparkles" aria-hidden="true"></i></div>
            <div class="bubble">
              <p>您好！我是活动分析助手。</p>
              <p>请告诉我您想分析的活动类型或具体问题，我会自动匹配相关活动并生成专业分析报告。</p>
            </div>
          </div>

          <div v-for="(message, index) in dynamicMessages" :key="index">
            <!-- 用户 / AI 消息 -->
            <div v-if="message.role === 'user' || message.role === 'ai'" class="msg-row" :class="{ user: message.role === 'user' }">
              <div class="avatar" :class="message.role === 'user' ? 'av-user' : 'av-ai'">
                <template v-if="message.role === 'user'">我</template>
                <i v-else class="ti ti-sparkles" aria-hidden="true"></i>
              </div>
              <div class="bubble" :class="{ user: message.role === 'user' }">
                <template v-if="message.role === 'user'">
                  <div v-if="message.selectedRows?.length" class="user-selected-row-chips">
                    <span
                      v-for="rowNumber in message.selectedRows"
                      :key="rowNumber"
                      class="selected-row-circle"
                    >{{ rowNumber }}</span>
                  </div>
                  <p v-if="message.text">{{ message.text }}</p>
                </template>
                <!-- AI 回复按 Markdown 渲染（renderMarkdown 先转义 HTML，v-html 安全） -->
                <template v-else>
                  <div
                    class="md-body"
                    :class="{ 'has-selectable-table': selectionActivities(message).length }"
                    @click="handleMarkdownActivityTableClick($event, message)"
                    v-html="renderMessageMarkdown(message)"
                  ></div>
                  <button
                    v-if="isDownloadableExportMessage(message)"
                    class="export-artifact-btn"
                    type="button"
                    @click="downloadExportArtifact(message.exportArtifact)"
                  >
                    <i class="ti ti-download" aria-hidden="true"></i>
                    下载 {{ (message.exportArtifact.format || 'HTML').toUpperCase() }} 报告
                  </button>
                  <div v-if="selectionActivities(message).length" class="inline-table-bulk-actions">
                    <span>已选 {{ (message.selectedIds || []).length }} 行</span>
                    <button
                      type="button"
                      :disabled="allActivitySelectionChecked(message)"
                      @click="setAllActivityRows(message, true)"
                    >全选</button>
                    <button
                      type="button"
                      :disabled="!(message.selectedIds || []).length"
                      @click="setAllActivityRows(message, false)"
                    >全不选</button>
                  </div>
                </template>
              </div>
            </div>

            <!-- 实时过程消息 -->
            <div v-else-if="message.role === 'system'" class="msg-row system-row">
              <div style="width: 34px; flex-shrink: 0"></div>
              <div class="system-msg">
                <i class="ti ti-cpu" aria-hidden="true"></i>
                <span>{{ message.text }}</span>
              </div>
            </div>

            <!-- 审批请求卡片 -->
            <div v-else-if="message.role === 'approval_request'" class="msg-row">
              <div class="avatar av-ai"><i class="ti ti-help-hexagon" aria-hidden="true"></i></div>
              <div class="activity-select-card">
                <div class="activity-select-head">
                  <div>
                    <div class="activity-select-title">{{ message.displayName }}</div>
                    <div class="activity-select-sub">{{ message.description || '请确认是否执行该操作' }}</div>
                  </div>
                  <button
                    v-if="message.resolved"
                    class="approval-collapse-toggle"
                    type="button"
                    :aria-label="message.expanded ? '折叠审批内容' : '展开审批内容'"
                    @click="message.expanded = !message.expanded"
                  >
                    <i :class="message.expanded ? 'ti ti-chevron-up' : 'ti ti-chevron-down'" aria-hidden="true"></i>
                  </button>
                </div>
                <div v-if="!message.resolved || message.expanded" class="activity-select-list">
                  <div
                    v-for="(activity, activityIndex) in message.activities"
                    :key="activityId(activity)"
                    class="activity-preview-item"
                  >
                    <div class="activity-preview-head">
                      <span class="activity-row-number">{{ activityRowNumber(activity, activityIndex) }}</span>
                      <span class="activity-preview-name">{{ activityName(activity) }}</span>
                      <span v-if="activityId(activity)" class="activity-preview-id">{{ activityId(activity) }}</span>
                    </div>
                  </div>
                  <div v-if="!message.activities?.length" class="activity-preview-item approval-description">
                    <div class="activity-preview-summary" style="white-space: pre-line;">{{ formatApprovalDescription(message) }}</div>
                  </div>
                </div>
                <div v-if="!message.resolved" class="activity-select-actions" style="margin-top: 16px; padding: 0 14px 14px;">
                  <button
                    class="activity-select-action"
                    style="min-width: 64px;"
                    type="button"
                    :disabled="activeConversation.typing"
                    @click="resolveApproval(message, 'reject')"
                  >
                    拒绝
                  </button>
                  <button
                    class="activity-continue-btn"
                    style="min-width: 64px;"
                    type="button"
                    :disabled="activeConversation.typing"
                    @click="resolveApproval(message, 'approve')"
                  >
                    确认
                  </button>
                </div>
                <div v-if="message.resolved" class="activity-select-actions" style="margin-top: 16px; padding: 0 14px 14px;">
                  <span class="activity-preview-summary">已{{ message.decision === 'approve' ? '确认' : '拒绝' }}</span>
                </div>
              </div>
            </div>

            <div v-else-if="message.role === 'html_report'" class="msg-row">
              <div class="avatar av-ai"><i class="ti ti-file-analytics" aria-hidden="true"></i></div>
              <div class="html-report-card">
                <div class="html-report-head">
                  <div>
                    <div class="html-report-title">{{ message.title }}</div>
                    <div class="html-report-sub">可新页签全屏预览，并下载 PNG 或 HTML 报告</div>
                  </div>
                  <div class="html-report-actions">
                    <button class="html-download-btn secondary" type="button" @click="openHtmlReportInNewTab(message)">
                      <i class="ti ti-external-link" aria-hidden="true"></i>全屏
                    </button>
                    <button
                      v-if="message.html"
                      class="html-download-btn secondary"
                      type="button"
                      title="使用当前浏览器生成一张完整的长图"
                      :disabled="exportOverlay.visible"
                      @click="downloadPngReport(message, $event)"
                    >
                      <i class="ti ti-photo" aria-hidden="true"></i>下载 PNG
                    </button>
                    <button
                      v-if="message.html"
                      class="html-download-btn"
                      type="button"
                      :disabled="exportOverlay.visible"
                      @click="downloadHtmlReport(message)"
                    >
                      <i class="ti ti-download" aria-hidden="true"></i>下载 HTML
                    </button>
                    <div class="report-feedback-actions" :title="canSubmitReportFeedback(message) ? '评价本次报告，再次点击可取消，也可切换评价' : '暂无运行记录，无法记录反馈'">
                      <button
                        class="report-feedback-btn"
                        :class="{ active: message.feedback === 'like' }"
                        type="button"
                        :disabled="!canSubmitReportFeedback(message) || message.feedbackSaving"
                        aria-label="点赞报告"
                        @click="handleReportFeedback(message, 'like')"
                      >
                        <i class="ti ti-thumb-up" aria-hidden="true"></i>
                      </button>
                      <button
                        class="report-feedback-btn"
                        :class="{ active: message.feedback === 'dislike', negative: true }"
                        type="button"
                        :disabled="!canSubmitReportFeedback(message) || message.feedbackSaving"
                        aria-label="点踩报告"
                        @click="handleReportFeedback(message, 'dislike')"
                      >
                        <i class="ti ti-thumb-down" aria-hidden="true"></i>
                      </button>
                    </div>
                  </div>
                </div>
                <div v-if="message.versionNo || message.reportContext" class="html-report-version-bar">
                  <span class="version-badge">v{{ message.versionNo || message.reportContext?.version || 1 }}版本</span>
                  <span v-if="message.reportContext && (message.reportContext.history || []).length > 1" class="version-history-toggle"
                        @click="message.showHistory = !message.showHistory">
                    修改历史（{{ message.reportContext.history.length }} 条）
                  </span>
                </div>
                <div v-if="message.reportContext && message.showHistory" class="html-report-history">
                  <div v-for="(item, idx) in message.reportContext.history" :key="idx" class="history-item">
                    <span class="history-version">v{{ item.version || 1 }}版本</span>
                    <span class="history-action">{{ item.action === 'generate' ? '生成' : '修改' }}</span>
                    <span class="history-summary">{{ item.diff_summary || '-' }}</span>
                  </div>
                </div>
                <div v-if="message.feedbackError" class="html-report-feedback-error">
                  {{ message.feedbackError }}
                </div>
                <div v-if="message.commentEditorOpen" class="report-feedback-comment">
                  <textarea
                    v-model="message.feedbackCommentDraft"
                    class="report-feedback-comment-input"
                    rows="3"
                    maxlength="500"
                    placeholder="可填写点踩原因（选填，≤500 字）"
                  ></textarea>
                  <div class="report-feedback-comment-actions">
                    <button
                      class="report-feedback-comment-btn"
                      type="button"
                      :disabled="message.feedbackSaving"
                      @click="submitDislikeFeedback(message, true)"
                    >
                      跳过
                    </button>
                    <button
                      class="report-feedback-comment-btn primary"
                      type="button"
                      :disabled="message.feedbackSaving"
                      @click="submitDislikeFeedback(message, false)"
                    >
                      提交
                    </button>
                  </div>
                </div>
                <iframe
                  class="html-report-preview"
                  :srcdoc="buildHtmlDocument(message)"
                  title="HTML报告预览"
                  sandbox="allow-scripts"
                ></iframe>
              </div>
            </div>

            <!-- 执行过程面板 -->
            <div v-else-if="message.role === 'execution_trace' && shouldDisplayThinkingTrace(message)" :data-trace-index="index" class="msg-row trace-row">
              <div style="width: 34px; flex-shrink: 0"></div>
              <div class="trace-panel">
                <button
                  class="trace-toggle"
                  :class="{ running: message.status === 'running' }"
                  type="button"
                  @click="message.expanded = !message.expanded"
                >
                  <ThinkingStatusIcon
                    class="trace-think-icon"
                    :status="message.status"
                  />
                  <span class="trace-progress">{{ traceProgressText(message) }}</span>
                  <span class="trace-title-text">{{ thinkingTitleText(message) }}</span>
                  <span class="trace-count">{{ visibleTraceSteps(message).length }} 个过程</span>
                  <i class="trace-chevron" :class="message.expanded ? 'ti ti-chevron-down' : 'ti ti-chevron-right'" aria-hidden="true"></i>
                </button>
                <div v-if="message.expanded" class="trace-content">
                  <div v-for="(step, idx) in visibleTraceSteps(message)" :key="stepKey(step) || idx" class="trace-step">
                    <div class="trace-step-dot"></div>
                    <div class="trace-step-body">
                      <div class="trace-step-title">{{ step.displayName }}</div>
                      <div class="trace-step-message">{{ step.message }}</div>
                      <div v-if="isTraceNode(step, 'intent_recognition') && step.payload && step.payload.marketing_intent" class="trace-step-detail">
                        <div class="detail-label">意图识别</div>
                        <div class="detail-value">{{ step.payload.marketing_intent.intent_type }} — {{ step.payload.marketing_intent.scene }}</div>
                      </div>
                      <div v-if="showTemplateListDetail(step)" class="trace-step-detail">
                        <div class="detail-label">分析能力</div>
                        <div v-if="isPendingStep(step)" class="detail-value">等待执行</div>
                        <details v-else-if="templateListNames(step).length" class="capability-list">
                          <summary>
                            <i class="ti ti-chevron-right capability-list-chevron" aria-hidden="true"></i>
                            已加载 {{ templateListNames(step).length }} 项分析能力
                          </summary>
                          <div class="capability-list-body">
                            <span v-for="name in templateListNames(step)" :key="name" class="capability-chip">{{ name }}</span>
                          </div>
                        </details>
                        <div v-else class="detail-value">已加载 {{ step.payload.template_list.length }} 项分析能力</div>
                      </div>
                      <TraceTemplateMatch
                        v-if="showTemplateMatchDetail(step)"
                        label="分析模板匹配"
                        :pending="isPendingStep(step)"
                        :result="templateMatchResult(step)"
                        :candidates="templateMatchCandidates(step)"
                        empty-text="已根据活动数据完成分析模板匹配"
                      />
                      <TraceTemplateMatch
                        v-if="isTraceNode(step, 'activity_template_matching') && (isPendingStep(step) || activityTemplateMatchResult(step))"
                        label="报告分析框架"
                        :pending="isPendingStep(step)"
                        :result="activityTemplateMatchResult(step)"
                        :candidates="activityTemplateMatchResult(step) ? [activityTemplateMatchResult(step)] : []"
                        empty-text="已完成报告分析框架编排"
                      />
                      <div v-if="isTraceNode(step, 'outbound_activity_data_fetch')" class="trace-step-detail">
                        <div class="detail-label">外呼活动业务数据</div>
                        <div class="detail-value">{{ isPendingStep(step) ? '等待执行' : (step.payload.outbound_activity_data_found ? '已查询到匹配外呼活动数据，后续编排报告分析框架并生成HTML报告' : '未查询到匹配外呼活动数据') }}</div>
                      </div>
                      <div v-if="isTraceNode(step, 'selected_activity_router') && activityRouteSummary(step)" class="trace-step-detail">
                        <div class="detail-label">判断结果</div>
                        <div class="detail-value">{{ activityRouteSummary(step) }}</div>
                      </div>
                      <div v-if="isTraceNode(step, 'selected_activity_router') && isPendingStep(step)" class="trace-step-detail">
                        <div class="detail-label">已选择活动</div>
                        <div class="detail-value">等待执行</div>
                      </div>
                      <div v-if="['marketing_data_fetch', 'selected_activity_router'].includes(stepKey(step)) && !isPendingStep(step) && step.payload && step.payload.activity_list" class="trace-step-detail">
                        <div class="activity-list-preview">
                          <div
                            v-for="(activity, activityIndex) in visibleActivities(step.payload.activity_list)"
                            :key="activityId(activity) || activityName(activity)"
                            class="activity-preview-item"
                          >
                            <div class="activity-preview-head">
                              <span class="activity-row-number">{{ activityRowNumber(activity, activityIndex) }}</span>
                              <span class="activity-preview-name">{{ activityName(activity) }}</span>
                              <span v-if="activityId(activity)" class="activity-preview-id">{{ activityId(activity) }}</span>
                            </div>
                            <div v-if="activityPeriod(activity)" class="activity-preview-period">{{ activityPeriod(activity) }}</div>
                            <div v-if="activityTags(activity).length" class="activity-preview-tags">
                              <span
                                v-for="tag in activityTags(activity)"
                                :key="tag.key"
                                class="activity-preview-tag"
                                :class="[`is-${tag.kind}`, `tone-${tag.tone}`]"
                              >
                                {{ tag.label }}
                              </span>
                            </div>
                            <div v-if="activitySummary(activity)" class="activity-preview-summary">{{ activitySummary(activity) }}</div>
                          </div>
                          <div v-if="step.payload.activity_list.length > visibleActivities(step.payload.activity_list).length" class="activity-preview-more">
                            还有 {{ step.payload.activity_list.length - visibleActivities(step.payload.activity_list).length }} 个活动未展开
                          </div>
                        </div>
                        <div class="detail-label">{{ activityTraceLabel(step) }}</div>
                        <div class="detail-value">{{ step.payload.activity_list.length }} 个活动</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 打字动画（等待最终回复） -->
          <div v-if="activeConversation.typing && !hasRunningThinking(activeConversation)" class="msg-row">
            <div class="avatar av-ai"><i class="ti ti-sparkles" aria-hidden="true"></i></div>
            <div class="bubble"><div class="typing-dot"><span></span><span></span><span></span></div></div>
          </div>
        </section>

        <footer class="chat-input-area">
          <!-- 当前任务进度指示器：始终显示在底部，方便用户感知长任务进度 -->
          <div
            v-if="currentRunningTraceSnapshot"
            class="floating-task-progress"
            role="status"
            aria-live="polite"
            @click="scrollToRunningTrace"
          >
            <div class="floating-task-progress-main">
              <ThinkingStatusIcon
                class="floating-task-progress-icon"
                status="running"
              />
              <span class="floating-task-progress-step">{{ currentRunningTraceSnapshot.currentStepName }}</span>
              <span class="trace-progress floating-task-progress-badge">{{ currentRunningTraceSnapshot.progressText }}</span>
            </div>
            <div class="floating-task-progress-meta">
              <span>{{ currentRunningTraceSnapshot.title }}</span>
            </div>
          </div>

          <div v-if="quickPrompts.length" class="quick-prompt-row" aria-label="快捷提问">
            <button
              v-for="prompt in quickPrompts"
              :key="prompt"
              class="quick-prompt-chip"
              type="button"
              :title="prompt"
              @click="useQuickQuestionPrompt(prompt)"
            >
              {{ prompt }}
            </button>
          </div>

          <div
            class="deep-input-container"
            :class="{ dragging: draggingFile }"
            @dragenter.prevent="handleFileDragEnter"
            @dragover.prevent="handleFileDragOver"
            @dragleave.prevent="handleFileDragLeave"
            @drop.prevent="handleFileDrop"
          >
            <div
              class="input-resize-handle"
              :class="{ active: inputResizing }"
              role="separator"
              aria-orientation="horizontal"
              title="向上拖拽调整输入框高度"
              @pointerdown="startInputResize"
            >
              <span></span>
            </div>
            <div v-if="draggingFile" class="drag-upload-mask">
              <i class="ti ti-cloud-upload" aria-hidden="true"></i>
              <span>松开上传文件</span>
            </div>
            <div class="input-textarea-wrap">
              <div v-if="composerSelectedRows.length" class="composer-selected-row-chips">
                <span class="composer-selected-label">已选行</span>
                <button
                  v-for="rowNumber in composerSelectedRows"
                  :key="rowNumber"
                  class="selected-row-circle"
                  type="button"
                  :title="`取消选择第 ${rowNumber} 行`"
                  @click="removeComposerSelectedRow(rowNumber)"
                >{{ rowNumber }}</button>
              </div>
              <textarea
                ref="inputTextareaRef"
                v-model="inputText"
                class="deep-textarea"
                placeholder="输入分析需求，或针对报告追问..."
                rows="1"
                :style="{ height: `${inputTextareaHeight}px` }"
                :disabled="activeConversation.typing || hasPendingApproval"
                @keydown="handleKey"
              ></textarea>
              <div v-if="uploadedFile || uploadError" class="upload-status-row">
                <div v-if="uploadedFile" class="uploaded-file-chip">
                  <i class="ti ti-file-spreadsheet" aria-hidden="true"></i>
                  <span>{{ uploadedFile.file_name }}</span>
                  <button type="button" title="移除附件" aria-label="移除附件" @click="removeUploadedFile">
                    <i class="ti ti-x" aria-hidden="true"></i>
                  </button>
                </div>
                <div v-if="uploadError" class="upload-error">
                  <i class="ti ti-alert-circle" aria-hidden="true"></i>
                  <span>{{ uploadError }}</span>
                </div>
              </div>
            </div>
            <div class="input-tools-bar">
              <div class="tool-group">
                <input
                  ref="fileInputRef"
                  class="hidden-file-input"
                  type="file"
                  accept=".csv,.xls,.xlsx,.xlsm,.xltx,.xltm,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  @change="handleFileSelected"
                >
                <button
                  class="tool-icon-btn"
                  :class="{ active: uploadedFile }"
                  :title="uploadedFile ? '更换上传文件' : '上传活动数据文件'"
                  type="button"
                  :disabled="activeConversation.typing || uploadingFile || hasPendingApproval"
                  @click="triggerFileUpload"
                >
                  <i :class="uploadingFile ? 'ti ti-loader-2 spinning' : 'ti ti-paperclip'" aria-hidden="true"></i>
                </button>
                <!-- <button class="tool-icon-btn" title="选择活动" type="button"><i class="ti ti-calendar-event" aria-hidden="true"></i></button>
                <button class="tool-icon-btn" title="选择数据模板" type="button"><i class="ti ti-layout-cards" aria-hidden="true"></i></button>
                <button class="tool-icon-btn" title="选择SKILL" type="button"><i class="ti ti-brain" aria-hidden="true"></i></button> -->
              </div>
              <div class="tool-group">
                <span v-if="hasPendingApproval" class="input-hint input-hint-stop">等待审批…</span>
                <span v-else-if="!activeConversation.typing" class="input-hint">↵ 发送 · ⇧↵ 换行</span>
                <span v-else class="input-hint input-hint-stop">执行中…</span>
                <button
                  v-if="!activeConversation.typing"
                  class="send-btn-circle"
                  type="button"
                  aria-label="发送"
                  :disabled="!canSend || uploadingFile"
                  @click="sendMsg"
                >
                  <i class="ti ti-arrow-up" aria-hidden="true"></i>
                </button>
                <button
                  v-else
                  class="send-btn-circle stop-btn-circle"
                  type="button"
                  aria-label="停止"
                  @click="cancelRun"
                >
                  <i class="ti ti-square" aria-hidden="true"></i>
                </button>
              </div>
            </div>
          </div>
        </footer>
      </main>
    </div>
    <div
      v-if="exportOverlay.visible"
      class="report-export-overlay"
      role="status"
      aria-live="polite"
      :aria-label="exportOverlay.label"
    >
      <div class="report-export-loading">
        <i class="ti ti-loader-2 report-export-spinner" aria-hidden="true"></i>
        <span>{{ exportOverlay.label }}</span>
        <small>请稍候，不要关闭当前页面</small>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ui-chat-page { --P: #165DFF; --PL: #E8F0FF; --PH: #0E47CC; --BD: #E5E6EB; --BG: #F7F8FA; --T1: #1D2129; --T2: #4E5969; --T3: #86909C; --R: 10px; --RAI: 16px 16px 4px 16px; --RUSER: 16px 4px 16px 16px; height: 100vh; width: 100vw; overflow: hidden; background: var(--BG); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif; font-size: 13px; }
* { box-sizing: border-box; }
.shell { display: flex; height: 100vh; width: 100vw; background: #fff; overflow: hidden; }
.sidebar { width: 320px; background: var(--BG); border-right: .5px solid var(--BD); display: flex; flex-direction: column; flex-shrink: 0; transition: width .2s ease; }
.sidebar.collapsed { width: 72px; }
.sb-head { padding: 20px 16px 18px; border-bottom: .5px solid var(--BD); }
.sb-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 36px; }
.sb-logo { display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1; }
.sb-logo-ic { width: 32px; height: 32px; background: var(--P); border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.sb-logo-ic i { color: #fff; font-size: 16px; }
.sb-logo-text { min-width: 0; overflow: hidden; transition: opacity .16s ease, width .16s ease; }
.sb-logo-name { font-size: 14px; font-weight: 600; color: var(--T1); }
.sb-logo-sub { font-size: 10px; color: var(--T3); }
.collapse-btn { width: 34px; height: 34px; border: none; border-radius: 10px; background: transparent; color: var(--T3); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; transition: background .15s, color .15s; }
.collapse-btn i { font-size: 22px; }
.collapse-btn:hover { background: #fff; color: var(--P); }
.new-btn { width: 100%; height: 52px; display: flex; align-items: center; justify-content: center; gap: 10px; margin: 26px 0 0; padding: 0 18px; border-radius: 999px; border: .5px solid #DDE3F0; color: var(--T1); font-size: 15px; cursor: pointer; font-weight: 500; transition: background .16s, border-color .16s, box-shadow .16s; background: #fff; box-shadow: 0 2px 8px rgba(15, 23, 42, .08); }
.new-btn i { font-size: 18px; color: var(--T1); }
.new-btn:hover { background: #fff; border-color: #D6DCE8; box-shadow: 0 4px 14px rgba(15, 23, 42, .12); }
.sb-body { flex: 1; overflow-y: auto; padding-bottom: 12px; }
.sb-section { padding: 12px 16px 4px; font-size: 10px; color: var(--T3); font-weight: 600; letter-spacing: .5px; }
.sb-item { height: 44px; padding: 0 12px; border-radius: 10px; font-size: 13px; color: var(--T2); cursor: pointer; transition: background .15s, color .15s; margin: 0 10px 4px; display: flex; align-items: center; gap: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border: 0; background: transparent; font-weight: 500; }
.sb-item:hover, .sb-item.active { background: #fff; color: var(--P); }
.sb-item i { font-size: 15px; flex-shrink: 0; }
.sb-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left; }
.rename-btn, .delete-btn { width: 24px; height: 24px; border: none; border-radius: 7px; background: transparent; color: var(--T3); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; padding: 0; opacity: 0; visibility: hidden; pointer-events: none; transition: opacity .12s, background .15s, color .15s; }
.rename-btn i, .delete-btn i { font-size: 13px; }
.sb-item:hover .rename-btn, .sb-item.active .rename-btn, .sb-item:hover .delete-btn, .sb-item.active .delete-btn { opacity: 1; visibility: visible; pointer-events: auto; }
.rename-btn:hover { background: var(--PL); color: var(--P); }
.delete-btn:hover { background: #FFECE8; color: #D92D20; }
.rename-input { flex: 1; min-width: 0; height: 24px; border: 1px solid var(--P); border-radius: 6px; padding: 3px 6px; outline: none; background: #fff; color: var(--T1); font-size: 12px; font-family: inherit; }
.sb-meta { margin-left: auto; font-size: 10px; color: var(--T3); flex-shrink: 0; }
.sidebar.collapsed .sb-head { padding: 18px 12px; }
.sidebar.collapsed .sb-top { justify-content: center; flex-direction: column; gap: 12px; }
.sidebar.collapsed .sb-logo-text, .sidebar.collapsed .new-btn span, .sidebar.collapsed .sb-section, .sidebar.collapsed .sb-title, .sidebar.collapsed .sb-meta, .sidebar.collapsed .rename-btn, .sidebar.collapsed .delete-btn { display: none; }
.sidebar.collapsed .new-btn { width: 44px; height: 44px; margin: 20px auto 0; padding: 0; border-radius: 14px; box-shadow: 0 2px 8px rgba(15, 23, 42, .08); }
.sidebar.collapsed .new-btn i { color: var(--P); }
.sidebar.collapsed .sb-body { padding-top: 10px; overflow: hidden; }
.sidebar.collapsed .sb-item { width: 44px; height: 44px; margin: 0 auto 8px; padding: 0; justify-content: center; border-radius: 14px; }
.sidebar.collapsed .sb-item i { font-size: 18px; }
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; background: #fff; }
.chat-head { background: #fff; border-bottom: .5px solid var(--BD); padding: 14px 20px; display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.head-icon { width: 34px; height: 34px; border-radius: 10px; background: var(--P); display: flex; align-items: center; justify-content: center; color: #fff; font-size: 18px; }
.chat-head-title { font-size: 15px; font-weight: 600; color: var(--T1); }
.chat-head-sub { font-size: 12px; color: var(--T3); margin-top: 2px; }
.chat-head-badges { display: flex; gap: 8px; margin-left: auto; }
.cbadge { padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 500; display: inline-flex; align-items: center; gap: 5px; }
.cbadge-green { background: #E8FFEA; color: #27500A; }
.chat-body { flex: 1; overflow-y: auto; padding: 20px 24px; display: flex; flex-direction: column; gap: 18px; background: #fff; }
.msg-row { display: flex; gap: 12px; align-items: flex-start; }
.msg-row.user { flex-direction: row-reverse; }
.avatar { width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 600; }
.av-ai { background: var(--P); color: #fff; }
.av-user { background: #E8F0FF; color: #0C447C; }
.bubble { max-width: 70%; background: #fff; border: .5px solid var(--BD); border-radius: var(--RAI); padding: 12px 16px; font-size: 13px; color: var(--T1); line-height: 1.55; }
.bubble.user { background: var(--P); color: #fff; border-color: var(--P); border-radius: var(--RUSER); }
.bubble.user p { color: #fff; }
.bubble p { margin: 0; }
.bubble p + p { margin-top: 8px; }
.typing-dot { display: inline-flex; gap: 4px; align-items: center; padding: 4px 0; }
.typing-dot span { width: 7px; height: 7px; background: var(--T3); border-radius: 50%; animation: bounce 1.2s infinite; }
.typing-dot span:nth-child(2) { animation-delay: .2s; }
.typing-dot span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-5px); } }
.chat-input-area { flex-shrink: 0; padding: 16px 20px 20px; background: #fff; border-top: .5px solid var(--BD); }
.quick-prompt-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; overflow-x: auto; padding-bottom: 2px; scrollbar-width: thin; }
.quick-prompt-chip { flex: 0 0 auto; max-width: 220px; height: 28px; padding: 0 10px; border: .5px solid var(--BD); border-radius: 999px; background: #fff; color: var(--T2); font-size: 12px; cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; transition: .15s; }
.quick-prompt-chip:hover { border-color: var(--P); background: var(--PL); color: var(--P); }
.deep-input-container { position: relative; background: #fff; border: 1px solid var(--BD); border-radius: 20px; transition: all .2s; box-shadow: 0 1px 2px rgba(0,0,0,.02); }
.deep-input-container:focus-within { border-color: var(--P); box-shadow: 0 0 0 2px rgba(22,93,255,.1); }
.deep-input-container.dragging { border-color: var(--P); box-shadow: 0 0 0 3px rgba(22,93,255,.12); }
.input-resize-handle { height: 12px; display: flex; align-items: center; justify-content: center; cursor: ns-resize; touch-action: none; border-radius: 20px 20px 0 0; }
.input-resize-handle span { width: 42px; height: 3px; border-radius: 999px; background: #D7DAE0; transition: .15s; }
.input-resize-handle:hover span, .input-resize-handle.active span { background: var(--P); }
.drag-upload-mask { position: absolute; inset: 6px; z-index: 3; display: flex; align-items: center; justify-content: center; gap: 8px; border: 1px dashed var(--P); border-radius: 16px; background: rgba(242, 247, 255, .94); color: var(--P); font-size: 13px; font-weight: 600; pointer-events: none; }
.drag-upload-mask i { font-size: 18px; }
.input-textarea-wrap { padding: 4px 16px 0; }
.composer-selected-row-chips { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; padding: 4px 0 8px; }
.composer-selected-label { margin-right: 2px; color: var(--T3); font-size: 11px; }
.selected-row-circle { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; padding: 0; border: 1px solid #8fb5ff; border-radius: 50%; background: #e8f0ff; color: var(--P); font-size: 12px; font-weight: 700; line-height: 1; }
button.selected-row-circle { cursor: pointer; transition: transform .12s, background .12s; }
button.selected-row-circle:hover { background: #d8e7ff; transform: translateY(-1px); }
.user-selected-row-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 7px; }
.bubble.user .user-selected-row-chips .selected-row-circle { border-color: rgba(255,255,255,.72); background: rgba(255,255,255,.16); color: #fff; }
.deep-textarea { width: 100%; border: none; outline: none; resize: none; font-size: 14px; line-height: 1.5; color: var(--T1); font-family: inherit; background: transparent; max-height: 180px; min-height: 24px; }
.deep-textarea::placeholder { color: var(--T3); font-size: 13px; }
.hidden-file-input { display: none; }
.upload-status-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 8px; }
.uploaded-file-chip { max-width: 100%; height: 30px; display: inline-flex; align-items: center; gap: 7px; padding: 0 6px 0 10px; border-radius: 999px; background: #F2F7FF; color: var(--T2); border: .5px solid #C8D9FF; font-size: 12px; }
.uploaded-file-chip > span { min-width: 0; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.uploaded-file-chip i { color: var(--P); font-size: 15px; flex-shrink: 0; }
.uploaded-file-chip button { width: 22px; height: 22px; border: none; border-radius: 50%; background: transparent; color: var(--T3); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 0; flex-shrink: 0; }
.uploaded-file-chip button:hover { background: #E3ECFF; color: var(--P); }
.upload-error { display: inline-flex; align-items: center; gap: 6px; color: #D92D20; font-size: 12px; }
.input-tools-bar { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px 10px 16px; }
.tool-group { display: flex; align-items: center; gap: 6px; }
.tool-icon-btn { width: 32px; height: 32px; border-radius: 50%; border: none; background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; color: var(--T3); transition: all .2s; }
.tool-icon-btn:hover { background: var(--BG); color: var(--T1); }
.tool-icon-btn.active { background: var(--PL); color: var(--P); }
.tool-icon-btn:disabled { cursor: not-allowed; opacity: .55; }
.tool-icon-btn:disabled:hover { background: transparent; color: var(--T3); }
.send-btn-circle { width: 34px; height: 34px; border-radius: 50%; background: var(--P); border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .2s; box-shadow: 0 2px 6px rgba(22,93,255,.2); }
.send-btn-circle:hover { background: var(--PH); transform: scale(1.02); }
.send-btn-circle:disabled { background: #c9cdd4; cursor: not-allowed; transform: none; box-shadow: none; }
.stop-btn-circle { background: #D92D20; box-shadow: 0 2px 6px rgba(217,45,32,.25); }
.stop-btn-circle:hover { background: #B91C1C; transform: scale(1.02); }
.input-hint-stop { color: #D92D20; }
.send-btn-circle i { color: #fff; font-size: 16px; }
.input-hint { font-size: 11px; color: var(--T3); margin-left: 8px; }
.divider-msg { text-align: center; font-size: 11px; color: var(--T3); display: flex; align-items: center; gap: 12px; }
.divider-msg::before, .divider-msg::after { content: ""; flex: 1; height: .5px; background: var(--BD); }
.ui-chat-page ::-webkit-scrollbar { width: 5px; }
.ui-chat-page ::-webkit-scrollbar-track { background: #f1f1f1; }
.ui-chat-page ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
/* ---- 实时过程消息 ---- */
.system-row { align-items: center; margin-top: -10px; }
.system-msg { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px; background: var(--BG); font-size: 11px; color: var(--T3); line-height: 1.4; }
.system-msg i { font-size: 12px; color: var(--P); }
.export-artifact-btn { margin-top: 12px; height: 36px; padding: 0 16px; border: none; border-radius: 8px; background: var(--P); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 7px; }
.export-artifact-btn:hover { background: var(--PH); }

/* ---- HTML报告卡片 ---- */
.html-report-card { width: min(860px, calc(100% - 46px)); border: .5px solid var(--BD); border-radius: 12px; background: #fff; overflow: hidden; box-shadow: 0 8px 24px rgba(15,23,42,.06); }
.html-report-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-bottom: .5px solid var(--BD); background: var(--BG); }
.html-report-head > div:first-child { min-width: 0; }
.html-report-title { font-size: 14px; font-weight: 700; color: var(--T1); }
.html-report-sub { margin-top: 2px; font-size: 11px; color: var(--T3); }
.html-report-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex: 0 0 auto; flex-wrap: nowrap; }
.report-feedback-actions { display: inline-flex; align-items: center; gap: 6px; }
.report-feedback-btn { width: 38px; height: 38px; border: .5px solid var(--BD); border-radius: 10px; background: #fff; color: var(--T3); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; transition: background .15s, border-color .15s, color .15s; }
.report-feedback-btn i { font-size: 21px; }
.report-feedback-btn:hover:not(:disabled) { border-color: #bcd0ff; color: var(--P); background: #f5f8ff; }
.report-feedback-btn.active { color: #166534; background: #f0fdf4; border-color: #bbf7d0; }
.report-feedback-btn.negative.active { color: #b42318; background: #fff1f2; border-color: #fecdd3; }
.report-feedback-btn:disabled { cursor: not-allowed; opacity: .48; }
.html-report-feedback-error { padding: 7px 14px; border-bottom: .5px solid #fecdd3; background: #fff1f2; color: #b42318; font-size: 11px; }
.report-feedback-comment { padding: 10px 14px; border-bottom: .5px solid var(--BD); background: #f8fafc; display: flex; flex-direction: column; gap: 8px; }
.report-feedback-comment-input { width: 100%; resize: vertical; min-height: 56px; border: .5px solid var(--BD); border-radius: 8px; padding: 8px 10px; outline: none; background: #fff; color: var(--T1); font-size: 12px; line-height: 1.6; font-family: inherit; }
.report-feedback-comment-input:focus { border-color: var(--P); box-shadow: 0 0 0 2px rgba(22, 93, 255, .08); }
.report-feedback-comment-actions { display: flex; justify-content: flex-end; gap: 8px; }
.report-feedback-comment-btn { height: 28px; padding: 0 12px; border: .5px solid var(--BD); border-radius: 8px; background: #fff; color: var(--T2); font-size: 12px; font-weight: 600; cursor: pointer; }
.report-feedback-comment-btn:hover:not(:disabled) { border-color: var(--P); color: var(--P); }
.report-feedback-comment-btn.primary { background: var(--P); border-color: var(--P); color: #fff; }
.report-feedback-comment-btn.primary:hover:not(:disabled) { color: #fff; filter: brightness(1.05); }
.report-feedback-comment-btn:disabled { opacity: .48; cursor: not-allowed; }
.html-download-btn { height: 32px; padding: 0 12px; border: none; border-radius: 8px; background: var(--P); color: #fff; font-size: 12px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 6px; flex-shrink: 0; }
.html-download-btn:hover { background: var(--PH); }
.html-download-btn.secondary { border: .5px solid var(--BD); background: #fff; color: var(--T2); }
.html-download-btn.secondary:hover { border-color: var(--P); background: #eff6ff; color: var(--P); }
.html-download-btn:disabled { cursor: wait; opacity: .58; }
.html-report-preview { display: block; width: 100%; min-height: 360px; max-height: 1400px; border: 0; background: #fff; }
.report-export-overlay { position: fixed; inset: 0; z-index: 9999; display: flex; align-items: center; justify-content: center; padding: 24px; background: rgba(15, 23, 42, .34); backdrop-filter: blur(2px); }
.report-export-loading { min-width: 240px; display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 24px 28px; border: .5px solid rgba(255, 255, 255, .7); border-radius: 14px; background: rgba(255, 255, 255, .96); color: var(--T1); font-size: 14px; font-weight: 700; box-shadow: 0 18px 48px rgba(15, 23, 42, .2); }
.report-export-loading small { color: var(--T3); font-size: 11px; font-weight: 400; }
.report-export-spinner { color: var(--P); font-size: 34px; animation: spin .9s linear infinite; }

/* ---- 活动选择卡片 ---- */
.activity-select-card { width: min(760px, calc(100% - 46px)); border: .5px solid var(--BD); border-radius: 12px; background: #fff; overflow: hidden; box-shadow: 0 8px 24px rgba(15,23,42,.06); }
.activity-select-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-bottom: .5px solid var(--BD); background: var(--BG); }
.activity-select-title { font-size: 14px; font-weight: 700; color: var(--T1); }
.activity-select-sub { margin-top: 2px; font-size: 11px; color: var(--T3); }
.activity-select-actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.approval-collapse-toggle { width: 28px; height: 28px; border: 0; border-radius: 7px; background: transparent; color: var(--T2); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
.approval-collapse-toggle:hover { background: #fff; color: var(--P); }
.activity-select-action { height: 32px; padding: 0 10px; border: .5px solid var(--BD); border-radius: 8px; background: #fff; color: var(--T2); font-size: 12px; font-weight: 600; cursor: pointer; flex-shrink: 0; }
.activity-select-action:hover { border-color: var(--P); color: var(--P); background: #eff6ff; }
.activity-select-action:disabled { color: var(--T3); background: #f2f3f5; cursor: not-allowed; }
.activity-continue-btn { height: 32px; padding: 0 12px; border: none; border-radius: 8px; background: var(--P); color: #fff; font-size: 12px; font-weight: 600; cursor: pointer; flex-shrink: 0; }
.activity-continue-btn:disabled { background: #c9cdd4; cursor: not-allowed; }
.activity-select-list { display: grid; gap: 8px; padding: 12px 14px; max-height: 420px; overflow: auto; }
.activity-select-item { display: flex; gap: 10px; align-items: flex-start; padding: 10px; border: .5px solid var(--BD); border-radius: 8px; background: #fff; cursor: pointer; }
.activity-select-item.selected { border-color: var(--P); background: var(--PL); }
.activity-select-item.disabled { cursor: default; opacity: .78; }
.activity-select-item input { flex-shrink: 0; margin-top: 2px; }
.activity-select-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.activity-row-number { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; flex: 0 0 22px; border-radius: 6px; background: #eef3ff; color: var(--P); font-size: 11px; font-weight: 700; line-height: 1; }

/* ---- 执行过程面板 ---- */
.trace-row { margin-top: 4px; }
.trace-panel { flex: 1; max-width: 760px; }
.trace-toggle { display: inline-flex; align-items: center; gap: 8px; padding: 4px 0; border: none; background: transparent; font-size: 14px; color: var(--T2); cursor: pointer; transition: .15s; }
.trace-toggle:hover { color: var(--P); }
.trace-toggle.running { color: var(--T1); }
.trace-think-icon { width: 28px; height: 28px; flex-shrink: 0; }
.trace-title-text { font-size: 15px; font-weight: 600; color: var(--T1); }
.trace-count { display: none; }
.trace-progress { padding: 1px 7px; border-radius: 999px; background: var(--BG); color: var(--T2); font-size: 12px; font-weight: 600; }
.trace-chevron { font-size: 14px; color: var(--T3); }
.trace-content { margin-top: 8px; padding: 12px 14px; background: var(--BG); border-radius: 10px; border: .5px solid var(--BD); }

/* ---- 底部浮动任务进度指示器 ---- */
.floating-task-progress {
  margin-bottom: 10px;
  padding: 8px 12px;
  background: #F0F7FF;
  border: 1px solid #C5D8FF;
  border-radius: 12px;
  cursor: pointer;
  transition: all .2s ease;
  user-select: none;
}
.floating-task-progress:hover {
  background: #E6F1FF;
  border-color: var(--P);
  box-shadow: 0 2px 8px rgba(22, 93, 255, .12);
}
.floating-task-progress-main {
  display: flex;
  align-items: center;
  gap: 8px;
}
.floating-task-progress-icon {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}
.floating-task-progress-step {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--T1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.floating-task-progress-badge {
  flex-shrink: 0;
  background: #fff;
}
.floating-task-progress-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--T2);
}

.trace-step { display: flex; gap: 10px; padding: 8px 0; border-bottom: .5px solid #E5E6EB; }
.trace-step:last-child { border-bottom: none; }
.trace-step-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--P); margin-top: 5px; flex-shrink: 0; }
.trace-step-body { flex: 1; min-width: 0; }
.trace-step-title { font-size: 12px; font-weight: 600; color: var(--T1); }
.trace-step-message { font-size: 11px; color: var(--T3); margin-top: 2px; }
.trace-step-detail { display: flex; flex-direction: column; margin-top: 6px; padding: 6px 10px; background: #fff; border-radius: 6px; border: .5px solid var(--BD); }
.detail-label { order: 1; font-size: 10px; color: var(--T3); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 2px; }
.detail-value { order: 2; font-size: 12px; color: var(--T1); font-weight: 500; }
.capability-list { order: 2; }
.capability-list summary { display: flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 500; color: var(--T1); cursor: pointer; list-style: none; user-select: none; }
.capability-list summary::-webkit-details-marker { display: none; }
.capability-list summary:hover { color: var(--P); }
.capability-list-chevron { font-size: 12px; color: var(--T3); transition: transform .15s ease; }
.capability-list[open] > summary .capability-list-chevron { transform: rotate(90deg); }
.capability-list-body { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.capability-chip { display: inline-flex; align-items: center; height: 22px; padding: 0 9px; border-radius: 999px; background: var(--BG); border: .5px solid var(--BD); color: var(--T2); font-size: 11px; font-weight: 500; line-height: 1; white-space: nowrap; }
.activity-list-preview { order: 3; display: grid; gap: 8px; margin: 8px 0 0; }
.activity-preview-item { padding: 8px 10px; border: .5px solid var(--BD); border-radius: 8px; background: var(--BG); }
.activity-preview-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; width: 100%; min-width: 0; }
.activity-preview-name { flex: 1; min-width: 0; font-size: 12px; font-weight: 700; color: var(--T1); line-height: 1.45; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.activity-preview-id { flex-shrink: 0; font-size: 10px; line-height: 1.4; color: var(--T3); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; text-align: right; }
.activity-preview-period { margin-top: 3px; font-size: 11px; color: var(--T3); }
.activity-preview-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.activity-preview-tag { display: inline-flex; align-items: center; height: 20px; padding: 0 7px; border-radius: 999px; background: #fff; border: .5px solid var(--BD); color: var(--T2); font-size: 10px; line-height: 1; font-weight: 600; white-space: nowrap; }
.activity-preview-tag.is-type { color: #0f766e; background: #f0fdfa; border-color: #99f6e4; }
.activity-preview-tag.tone-active { color: #166534; background: #f0fdf4; border-color: #bbf7d0; }
.activity-preview-tag.tone-pending { color: #92400e; background: #fffbeb; border-color: #fde68a; }
.activity-preview-tag.tone-closed { color: #475569; background: #f8fafc; border-color: #cbd5e1; }
.activity-preview-tag.tone-danger { color: #b42318; background: #fff1f2; border-color: #fecdd3; }
.activity-preview-summary { margin-top: 6px; color: var(--T2); font-size: 11px; line-height: 1.5; }
.activity-preview-item.approval-description .activity-preview-summary { color: var(--T1); font-size: 13px; }
.activity-preview-more { padding: 4px 2px 0; color: var(--T3); font-size: 11px; }

/* AI 回复 Markdown 渲染（v-html 注入内容无 data-v 属性，必须用 :deep() 穿透 scoped） */
.md-body { line-height: 1.6; }
.md-body :deep(> :first-child) { margin-top: 0; }
.md-body :deep(> :last-child) { margin-bottom: 0; }
.md-body :deep(p) { margin: 6px 0; }
.md-body :deep(h1), .md-body :deep(h2), .md-body :deep(h3), .md-body :deep(h4) { margin: 12px 0 6px; font-weight: 700; color: var(--T1); line-height: 1.35; }
.md-body :deep(h1) { font-size: 16px; }
.md-body :deep(h2) { font-size: 15px; }
.md-body :deep(h3) { font-size: 14px; }
.md-body :deep(h4) { font-size: 13px; }
.md-body :deep(strong) { font-weight: 700; color: var(--T1); }
.md-body :deep(ul), .md-body :deep(ol) { margin: 6px 0; padding-left: 20px; }
.md-body :deep(li) { margin: 3px 0; }
.md-body :deep(code) { padding: 1px 5px; border-radius: 4px; background: var(--BG, #f3f4f6); border: .5px solid var(--BD); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
.md-body :deep(pre) { margin: 8px 0; padding: 10px 12px; border-radius: 8px; background: #0f172a; overflow-x: auto; }
.md-body :deep(pre) :deep(code) { padding: 0; background: transparent; border: none; color: #e2e8f0; font-size: 12px; line-height: 1.5; }
.md-body :deep(blockquote) { margin: 8px 0; padding: 6px 12px; border-left: 3px solid var(--P); background: var(--BG, #f8fafc); border-radius: 0 6px 6px 0; color: var(--T2); }
.md-body :deep(table) { margin: 8px 0; border-collapse: collapse; width: 100%; font-size: 12px; }
.md-body :deep(th), .md-body :deep(td) { padding: 6px 10px; border: .5px solid var(--BD); text-align: left; line-height: 1.45; }
.md-body :deep(th) { background: var(--BG, #f3f4f6); font-weight: 700; color: var(--T1); white-space: nowrap; }
.md-body :deep(tr:nth-child(even)) :deep(td) { background: rgba(0, 0, 0, .015); }
.md-body.has-selectable-table :deep(tbody tr.is-selectable) { cursor: pointer; transition: background .15s, box-shadow .15s; }
.md-body.has-selectable-table :deep(tbody tr.is-selectable:hover td) { background: #f2f7ff; }
.md-body.has-selectable-table :deep(tbody tr.is-selectable.is-selected td) { background: #e8f0ff; box-shadow: inset 0 1px #8fb5ff, inset 0 -1px #8fb5ff; }
.md-body.has-selectable-table :deep(tbody tr.is-selectable.is-selected td:first-child) { box-shadow: inset 2px 0 var(--P), inset 0 1px #8fb5ff, inset 0 -1px #8fb5ff; color: var(--P); font-weight: 700; }
.md-body.has-selectable-table :deep(tbody tr.is-selectable.is-selected td:last-child) { box-shadow: inset -1px 0 #8fb5ff, inset 0 1px #8fb5ff, inset 0 -1px #8fb5ff; }
.inline-table-bulk-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.inline-table-bulk-actions span { margin-right: auto; color: var(--T3); font-size: 11px; }
.inline-table-bulk-actions button { height: 28px; padding: 0 10px; border: .5px solid var(--BD); border-radius: 8px; background: #fff; color: var(--T2); font-size: 11px; font-weight: 600; cursor: pointer; }
.inline-table-bulk-actions button:hover:not(:disabled) { border-color: var(--P); background: #eff6ff; color: var(--P); }
.inline-table-bulk-actions button:disabled { opacity: .45; cursor: not-allowed; }
.md-body :deep(a) { color: var(--P); text-decoration: underline; }

.html-report-version-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid #e2e8f0;
}
.version-badge {
  background: #0f172a;
  color: #fff;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
}
.version-history-toggle {
  color: #2563eb;
  cursor: pointer;
  font-size: 13px;
}
.html-report-history {
  padding: 8px 16px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}
.history-item {
  display: flex;
  gap: 12px;
  font-size: 13px;
  color: #475569;
}
.history-action {
  color: #0f172a;
  font-weight: 500;
}
.history-summary {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 860px) { .sidebar { display: none; } .bubble { max-width: 86%; } .chat-head-badges { display: none; } .trace-panel { max-width: 100%; } .html-report-card { width: calc(100% - 46px); } }
</style>

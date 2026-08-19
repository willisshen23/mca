<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import {
  fetchConversations,
  createConversationAPI,
  deleteConversationAPI,
  renameConversationAPI,
  getUserId
} from '@/api/conversations.js';
import { uploadFile } from '@/api/files.js';
import { fetchQuickPrompts } from '@/api/quickPrompts.js';
import { useChatUrlParams } from '@/composables/useChatUrlParams';
import { useAgentChat } from '@/composables/useAgentChat.js';
import {
  installHtmlReportBridges, cancelPendingPngExports, reportExportOverlay
} from '@/utils/htmlReport.js';
import ThinkingStatusIcon from '@/components/common/ThinkingStatusIcon.vue';
import ChatMessageList from '@/components/chat/ChatMessageList.vue';

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
let uninstallReportBridges = null;
const sidebarCollapsed = ref(false);
const inputTextareaHeight = ref(24);
const inputResizing = ref(false);
const ACCEPTED_UPLOAD_EXTENSIONS = ['.csv', '.xls', '.xlsx', '.xlsm', '.xltx', '.xltm'];
const INPUT_TEXTAREA_MIN_HEIGHT = 24;
const INPUT_TEXTAREA_MAX_HEIGHT = 180;
const DEFAULT_QUICK_QUESTION_PROMPTS = [
  '帮我生成一份2026年7月“薪运年终奖代发活动”的分析报告',
  '分析一下“薪运年终奖代发活动”并生成报告',
  '基于上传的数据生成活动分析报告'
];
const quickPrompts = ref([...DEFAULT_QUICK_QUESTION_PROMPTS]);

const {
  userId: urlUserId,
  userName: urlUserName,
  orgNo: urlOrgNo,
  srcSysNo: urlSrcSysNo,
  channel: urlChannel
} = useChatUrlParams();

const conversations = ref([]);

const activeConversation = computed(() => (
  conversations.value.find((item) => item.id === activeConversationId.value) || conversations.value[0] || {}
));
const todayConversations = computed(() => conversations.value.filter((item) => item.group === 'today'));
const recentConversations = computed(() => conversations.value.filter((item) => item.group === 'recent'));

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
  loadConversation,
  removeComposerSelectedRow,
  composerSelectedRows,
  hasPendingApproval,
  // 流式对话引擎（Task 5 迁入 composable）
  sendMessage: chatSendMessage, cancelRun,
  recoverAgentRun, currentRunningTraceSnapshot
} = chat;

const createConversation = (init) => chat.createConversationState(init);

const canSend = computed(() =>
  !hasPendingApproval.value
  && (
    inputText.value.trim().length > 0
    || Boolean(uploadedFile.value?.file_path)
    || composerSelectedRows.value.length > 0
  )
);

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

onMounted(async () => {
  getUserId();
  uninstallReportBridges = installHtmlReportBridges();
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
    await loadConversation(conv);
  }
  if (conv) await recoverAgentRun(conv);
  scrollBottom();
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

// 薄包装：清理本地输入状态后委托给 composable 的 sendMessage（Task 8 前过渡）
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
  stopInputResize();
  uninstallReportBridges?.();
  cancelPendingPngExports();
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
                  @click="cancelRun()"
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
      v-if="reportExportOverlay.visible"
      class="report-export-overlay"
      role="status"
      aria-live="polite"
      :aria-label="reportExportOverlay.label"
    >
      <div class="report-export-loading">
        <i class="ti ti-loader-2 report-export-spinner" aria-hidden="true"></i>
        <span>{{ reportExportOverlay.label }}</span>
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
.ui-chat-page ::-webkit-scrollbar { width: 5px; }
.ui-chat-page ::-webkit-scrollbar-track { background: #f1f1f1; }
.ui-chat-page ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
/* ---- 报告导出遮罩（卡片本体样式已迁入 components/chat/HtmlReportCard.vue） ---- */
.report-export-overlay { position: fixed; inset: 0; z-index: 9999; display: flex; align-items: center; justify-content: center; padding: 24px; background: rgba(15, 23, 42, .34); backdrop-filter: blur(2px); }
.report-export-loading { min-width: 240px; display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 24px 28px; border: .5px solid rgba(255, 255, 255, .7); border-radius: 14px; background: rgba(255, 255, 255, .96); color: var(--T1); font-size: 14px; font-weight: 700; box-shadow: 0 18px 48px rgba(15, 23, 42, .2); }
.report-export-loading small { color: var(--T3); font-size: 11px; font-weight: 400; }
.report-export-spinner { color: var(--P); font-size: 34px; animation: spin .9s linear infinite; }

.trace-progress { padding: 1px 7px; border-radius: 999px; background: var(--BG); color: var(--T2); font-size: 12px; font-weight: 600; }
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

@media (max-width: 860px) { .sidebar { display: none; } .chat-head-badges { display: none; } }
</style>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { uploadFile } from '@/api/files.js';
import { fetchQuickPrompts } from '@/api/quickPrompts.js';
import ThinkingStatusIcon from '@/components/common/ThinkingStatusIcon.vue';

const props = defineProps({
  chat: { type: Object, required: true },
  conversation: { type: Object, required: true }
});
const emit = defineEmits(['locate-trace']);

const fileInputRef = ref(null);
const inputTextareaRef = ref(null);
const inputText = ref('');
const uploadedFile = ref(null);
const uploadingFile = ref(false);
const uploadError = ref('');
const draggingFile = ref(false);
const dragDepth = ref(0);
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

// composable 返回的 computed 包一层本地 computed，保证模板中自动解包
const composerSelectedRows = computed(() => props.chat.composerSelectedRows.value || []);
const hasPendingApproval = computed(() => props.chat.hasPendingApproval.value);
const currentRunningTraceSnapshot = computed(() => props.chat.currentRunningTraceSnapshot.value);
const removeComposerSelectedRow = (rowNumber) => props.chat.removeComposerSelectedRow(rowNumber);
const cancelRun = () => props.chat.cancelRun();

const canSend = computed(() =>
  !hasPendingApproval.value
  && (
    inputText.value.trim().length > 0
    || Boolean(uploadedFile.value?.file_path)
    || composerSelectedRows.value.length > 0
  )
);

onMounted(async () => {
  try {
    const remotePrompts = await fetchQuickPrompts();
    if (Array.isArray(remotePrompts)) {
      quickPrompts.value = remotePrompts;
    }
  } catch (e) {
    console.warn('加载快捷提问失败，使用默认话术', e);
  }
});

function triggerFileUpload() {
  if (props.conversation?.typing || uploadingFile.value) return;
  uploadError.value = '';
  fileInputRef.value?.click();
}

function canUploadNow() {
  return !props.conversation?.typing && !uploadingFile.value;
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
  if (props.conversation?.typing || uploadingFile.value) return;
  uploadedFile.value = null;
  uploadError.value = '';
}

async function sendMsg() {
  const text = inputText.value.trim();
  const currentUploadedFile = uploadedFile.value;
  const selectedRows = [...props.chat.composerSelectedRows.value];
  if (!text && !currentUploadedFile?.file_path && selectedRows.length === 0) return;
  if (props.conversation?.typing && !text && selectedRows.length === 0) return;
  inputText.value = '';
  uploadedFile.value = null;
  uploadError.value = '';
  await props.chat.sendMessage({ text, uploadedFile: currentUploadedFile, selectedRows });
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
});

defineExpose({
  focus: () => inputTextareaRef.value?.focus(),
  clear: () => { inputText.value = ''; }
});
</script>

<template>
  <footer class="chat-input-area">
    <!-- 当前任务进度指示器：始终显示在底部，方便用户感知长任务进度 -->
    <div
      v-if="currentRunningTraceSnapshot"
      class="floating-task-progress"
      role="status"
      aria-live="polite"
      @click="emit('locate-trace')"
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
          placeholder="输入分析需求，执行中也可发送插话调整任务..."
          rows="1"
          :style="{ height: `${inputTextareaHeight}px` }"
          :disabled="hasPendingApproval"
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
            :disabled="conversation?.typing || uploadingFile || hasPendingApproval"
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
          <span v-else-if="!conversation?.typing" class="input-hint">↵ 发送 · ⇧↵ 换行</span>
          <span v-else class="input-hint">↵ 发送插话 · ⇧↵ 换行</span>
          <button
            class="send-btn-circle"
            type="button"
            aria-label="发送"
            :disabled="!canSend || uploadingFile"
            @click="sendMsg"
          >
            <i class="ti ti-arrow-up" aria-hidden="true"></i>
          </button>
          <button
            v-if="conversation?.typing"
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
</template>

<style scoped>
.chat-input-area { flex-shrink: 0; padding: 16px 20px 20px; background: #fff; border-top: .5px solid var(--BD); }
.quick-prompt-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; overflow-x: auto; padding-bottom: 2px; scrollbar-width: thin; }
.quick-prompt-chip { flex: 0 0 auto; max-width: 220px; height: 28px; padding: 0 10px; border: .5px solid var(--BD); border-radius: var(--radius-pill); background: #fff; color: var(--T2); font-size: 12px; cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; transition: .15s; }
.quick-prompt-chip:hover { border-color: var(--P); background: var(--PL); color: var(--P); }
.deep-input-container { position: relative; background: #fff; border: 1px solid var(--BD); border-radius: var(--radius-xl); transition: all .2s; box-shadow: 0 1px 2px rgba(0,0,0,.02); }
.deep-input-container:focus-within { border-color: var(--P); box-shadow: var(--shadow-focus); }
.deep-input-container.dragging { border-color: var(--P); box-shadow: var(--shadow-focus); }
.input-resize-handle { height: 12px; display: flex; align-items: center; justify-content: center; cursor: ns-resize; touch-action: none; border-radius: 20px 20px 0 0; }
.input-resize-handle span { width: 42px; height: 3px; border-radius: var(--radius-pill); background: var(--border-strong); transition: .15s; }
.input-resize-handle:hover span, .input-resize-handle.active span { background: var(--P); }
.drag-upload-mask { position: absolute; inset: 6px; z-index: 3; display: flex; align-items: center; justify-content: center; gap: 8px; border: 1px dashed var(--P); border-radius: var(--radius-lg); background: rgba(242, 247, 255, .94); color: var(--P); font-size: 13px; font-weight: 600; pointer-events: none; }
.drag-upload-mask i { font-size: 18px; }
.input-textarea-wrap { padding: 4px 16px 0; }
.composer-selected-row-chips { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; padding: 4px 0 8px; }
.composer-selected-label { margin-right: 2px; color: var(--T3); font-size: 11px; }
/* 与 ChatMessageList 共用 .selected-row-circle 基础样式（两边 scoped 各持一份） */
.selected-row-circle { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; padding: 0; border: 1px solid var(--color-primary-border); border-radius: 50%; background: var(--color-primary-weak); color: var(--P); font-size: 12px; font-weight: 700; line-height: 1; }
button.selected-row-circle { cursor: pointer; transition: transform .12s, background .12s; }
button.selected-row-circle:hover { background: var(--color-primary-border); transform: translateY(-1px); }
.deep-textarea { width: 100%; border: none; outline: none; resize: none; font-size: 14px; line-height: 1.5; color: var(--T1); font-family: inherit; background: transparent; max-height: 180px; min-height: 24px; }
.deep-textarea::placeholder { color: var(--T3); font-size: 13px; }
.hidden-file-input { display: none; }
.upload-status-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 8px; }
.uploaded-file-chip { max-width: 100%; height: 30px; display: inline-flex; align-items: center; gap: 7px; padding: 0 6px 0 10px; border-radius: var(--radius-pill); background: var(--color-primary-weaker); color: var(--T2); border: .5px solid var(--color-primary-border); font-size: 12px; }
.uploaded-file-chip > span { min-width: 0; max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.uploaded-file-chip i { color: var(--P); font-size: 15px; flex-shrink: 0; }
.uploaded-file-chip button { width: 22px; height: 22px; border: none; border-radius: 50%; background: transparent; color: var(--T3); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; padding: 0; flex-shrink: 0; }
.uploaded-file-chip button:hover { background: var(--color-primary-weak); color: var(--P); }
.upload-error { display: inline-flex; align-items: center; gap: 6px; color: var(--color-danger); font-size: 12px; }
.input-tools-bar { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px 10px 16px; }
.tool-group { display: flex; align-items: center; gap: 6px; }
.tool-icon-btn { width: 32px; height: 32px; border-radius: 50%; border: none; background: transparent; cursor: pointer; display: flex; align-items: center; justify-content: center; color: var(--T3); transition: all .2s; }
.tool-icon-btn:hover { background: var(--BG); color: var(--T1); }
.tool-icon-btn.active { background: var(--PL); color: var(--P); }
.tool-icon-btn:disabled { cursor: not-allowed; opacity: .55; }
.tool-icon-btn:disabled:hover { background: transparent; color: var(--T3); }
.send-btn-circle { width: 34px; height: 34px; border-radius: 50%; background: var(--P); border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .2s; box-shadow: 0 2px 6px rgba(43, 110, 221,.2); }
.send-btn-circle:hover { background: var(--PH); transform: scale(1.02); }
.send-btn-circle:disabled { background: var(--border-strong); cursor: not-allowed; transform: none; box-shadow: none; }
.stop-btn-circle { background: var(--color-danger); box-shadow: 0 2px 6px rgba(217,45,32,.25); }
.stop-btn-circle:hover { background: var(--color-danger); transform: scale(1.02); }
.input-hint-stop { color: var(--color-danger); }
.send-btn-circle i { color: #fff; font-size: 16px; }
.input-hint { font-size: 11px; color: var(--T3); margin-left: 8px; }
/* 与 ChatMessageList 共用 .trace-progress 样式（两边 scoped 各持一份） */
.trace-progress { padding: 1px 7px; border-radius: var(--radius-pill); background: var(--BG); color: var(--T2); font-size: 12px; font-weight: 600; }
/* ---- 底部浮动任务进度指示器 ---- */
.floating-task-progress {
  margin-bottom: 10px;
  padding: 8px 12px;
  background: var(--color-primary-weaker);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all .2s ease;
  user-select: none;
}
.floating-task-progress:hover {
  background: var(--color-primary-weak);
  border-color: var(--P);
  box-shadow: var(--shadow-md);
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
</style>

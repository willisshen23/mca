<script setup>
import { computed, onMounted, ref } from 'vue';
import {
  fetchAdminQuickPrompts,
  saveAdminQuickPrompts
} from '../../api/quickPrompts.js';

const prompts = ref([]);
const loading = ref(false);
const saving = ref(false);
const error = ref('');
const dragOverIndex = ref(-1);

const hasEmptyText = computed(() => prompts.value.some((item) => !item.text.trim()));
const canSave = computed(() => !loading.value && !saving.value && !hasEmptyText.value);

function normalizeItem(item) {
  return {
    localId: item.id ?? `new-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    id: item.id,
    text: item.text || '',
    is_enabled: item.is_enabled !== false
  };
}

async function loadPrompts() {
  loading.value = true;
  error.value = '';
  try {
    const rows = await fetchAdminQuickPrompts();
    prompts.value = rows.map(normalizeItem);
  } catch (err) {
    error.value = err.message || '加载快捷提问失败';
  } finally {
    loading.value = false;
  }
}

function addPrompt() {
  prompts.value.push(normalizeItem({ text: '', is_enabled: true }));
}

function removePrompt(index) {
  prompts.value.splice(index, 1);
}

function movePrompt(fromIndex, toIndex) {
  if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0) return;
  const item = prompts.value.splice(fromIndex, 1)[0];
  prompts.value.splice(toIndex, 0, item);
}

function handleDragStart(event, index) {
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', String(index));
  event.target.closest('.quick-prompt-row')?.classList.add('dragging');
}

function handleDragEnd(event) {
  event.target.closest('.quick-prompt-row')?.classList.remove('dragging');
  dragOverIndex.value = -1;
}

function handleDragOver(event, index) {
  event.preventDefault();
  event.dataTransfer.dropEffect = 'move';
  dragOverIndex.value = index;
}

function handleDragLeave() {
  dragOverIndex.value = -1;
}

function handleDrop(event, targetIndex) {
  event.preventDefault();
  const sourceIndex = Number(event.dataTransfer.getData('text/plain'));
  movePrompt(sourceIndex, targetIndex);
  dragOverIndex.value = -1;
}

function buildPayload() {
  return prompts.value.map((item) => ({
    ...(item.id ? { id: item.id } : {}),
    text: item.text.trim(),
    is_enabled: item.is_enabled
  }));
}

async function save() {
  if (hasEmptyText.value) {
    error.value = '存在空文本话术，请填写完整后再保存';
    return;
  }
  saving.value = true;
  error.value = '';
  try {
    const rows = await saveAdminQuickPrompts(buildPayload());
    prompts.value = rows.map(normalizeItem);
  } catch (err) {
    error.value = err.message || '保存失败';
  } finally {
    saving.value = false;
  }
}

onMounted(loadPrompts);
</script>

<template>
  <div class="quick-prompt-manager">
    <div class="quick-prompt-toolbar">
      <div>
        <div class="quick-prompt-title">快捷提问配置</div>
        <div class="quick-prompt-subtitle">配置 chat-ui 输入框上方展示的推荐话术</div>
      </div>
      <button
        class="btn pri"
        type="button"
        :disabled="!canSave"
        @click="save"
      >
        <i class="ti ti-device-floppy"></i>
        {{ saving ? '保存中...' : '保存' }}
      </button>
    </div>

    <div v-if="error" class="itip quick-prompt-error">
      <i class="ti ti-alert-circle"></i>{{ error }}
    </div>

    <div v-if="loading" class="quick-prompt-empty">正在加载快捷提问...</div>

    <div v-else class="quick-prompt-list">
      <div
        v-for="(item, index) in prompts"
        :key="item.localId"
        class="quick-prompt-row"
        :class="{
          'drop-target': dragOverIndex === index,
          'has-error': !item.text.trim()
        }"
        draggable="true"
        @dragstart="handleDragStart($event, index)"
        @dragend="handleDragEnd"
        @dragover="handleDragOver($event, index)"
        @dragleave="handleDragLeave"
        @drop="handleDrop($event, index)"
      >
        <i class="ti ti-grip-vertical quick-prompt-drag-handle"></i>
        <input
          v-model="item.text"
          class="quick-prompt-input"
          type="text"
          placeholder="请输入推荐话术"
          maxlength="500"
        />
        <label class="quick-prompt-toggle">
          <input v-model="item.is_enabled" type="checkbox" />
          <span class="toggle-track">
            <span class="toggle-thumb"></span>
          </span>
          <span class="toggle-label">{{ item.is_enabled ? '启用' : '禁用' }}</span>
        </label>
        <button
          class="quick-prompt-delete"
          type="button"
          title="删除"
          @click="removePrompt(index)"
        >
          <i class="ti ti-trash"></i>
        </button>
      </div>

      <div v-if="!prompts.length" class="quick-prompt-empty">
        暂无快捷提问，点击下方按钮添加
      </div>
    </div>

    <div class="quick-prompt-footer">
      <button class="btn" type="button" :disabled="loading || saving" @click="addPrompt">
        <i class="ti ti-plus"></i>
        新增话术
      </button>
    </div>
  </div>
</template>

<style scoped>
.quick-prompt-manager {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.quick-prompt-toolbar {
  background: #fff;
  border-bottom: 1px solid var(--border);
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.quick-prompt-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--t1);
  margin-bottom: 4px;
}
.quick-prompt-subtitle {
  font-size: 12px;
  color: var(--t3);
}
.quick-prompt-error {
  margin: 10px 16px 0;
  border-color: #ffd0d0;
  background: #fff5f5;
  color: var(--danger);
}
.quick-prompt-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.quick-prompt-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 6px;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.quick-prompt-row.dragging {
  opacity: 0.5;
}
.quick-prompt-row.drop-target {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(22, 93, 255, 0.08);
}
.quick-prompt-row.has-error {
  border-color: var(--danger);
  background: #fff5f5;
}
.quick-prompt-drag-handle {
  font-size: 18px;
  color: var(--t3);
  cursor: grab;
  flex-shrink: 0;
}
.quick-prompt-drag-handle:active {
  cursor: grabbing;
}
.quick-prompt-input {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 7px 10px;
  font-size: 13px;
  color: var(--t1);
  background: #fff;
  outline: none;
}
.quick-prompt-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px rgba(22, 93, 255, 0.08);
}
.quick-prompt-row.has-error .quick-prompt-input {
  border-color: var(--danger);
}
.quick-prompt-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  flex-shrink: 0;
}
.quick-prompt-toggle input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
}
.toggle-track {
  width: 36px;
  height: 20px;
  background: #d9d9d9;
  border-radius: 999px;
  position: relative;
  transition: background 0.2s;
}
.quick-prompt-toggle input:checked + .toggle-track {
  background: var(--primary);
}
.toggle-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}
.quick-prompt-toggle input:checked + .toggle-track .toggle-thumb {
  transform: translateX(16px);
}
.toggle-label {
  font-size: 12px;
  color: var(--t2);
  min-width: 36px;
}
.quick-prompt-delete {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--t3);
  cursor: pointer;
  flex-shrink: 0;
}
.quick-prompt-delete:hover {
  background: #fff5f5;
  color: var(--danger);
}
.quick-prompt-footer {
  background: #fff;
  border-top: 1px solid var(--border);
  padding: 12px 16px;
}
.quick-prompt-empty {
  min-height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--t3);
  font-size: 13px;
}
@media (max-width: 760px) {
  .quick-prompt-row {
    flex-wrap: wrap;
  }
  .quick-prompt-input {
    width: 100%;
    flex: auto;
  }
}
</style>

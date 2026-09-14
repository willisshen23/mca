<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import ModalDialog from '../components/common/ModalDialog.vue';
import QuickPromptManager from '../components/settings/QuickPromptManager.vue';
import { fetchEnvConfig, restartBackend, updateEnvConfig } from '../api/envConfig';
import { fetchSystemPrompts, publishSystemPrompt, updateSystemPrompt } from '../api/systemPrompts';

const activeSection = ref('systemPrompt');
const keyword = ref('');
const statusFilter = ref('all');
const selectedPromptKey = ref('');
const prompts = ref([]);
const loading = ref(false);
const saving = ref(false);
const publishing = ref(false);
const error = ref('');
const envLoading = ref(false);
const envSaving = ref(false);
const envError = ref('');
const envPath = ref('');
const envRestartRequired = ref(false);
const envContent = ref('');
const envOriginalContent = ref('');
const restartModalOpen = ref(false);
const restartingBackend = ref(false);
const restartMessage = ref('');

const draft = reactive({
  id: null,
  name: '',
  promptKey: '',
  agentName: '',
  scenario: '',
  status: '',
  content: '',
  changeNote: ''
});

const sections = [
  { key: 'systemPrompt', name: '系统提示词', desc: '报告生成提示词', icon: 'ti-message-code' },
  { key: 'envConfig', name: '环境配置', desc: '.env 运行配置', icon: 'ti-settings-cog' },
  { key: 'quickPrompt', name: '快捷提问', desc: 'chat-ui 推荐话术', icon: 'ti-bolt' },
  { key: 'audit', name: '发布记录', desc: '发布审计与回滚', icon: 'ti-history' }
];

const selectedPrompt = computed(() => prompts.value.find((item) => item.promptKey === selectedPromptKey.value) || null);
const filteredPrompts = computed(() => prompts.value.filter((item) => {
  const word = keyword.value.trim();
  const matchKeyword = !word || item.name.includes(word) || item.promptKey.includes(word) || item.agentName.includes(word);
  const matchStatus = statusFilter.value === 'all' || item.status === statusFilter.value;
  return matchKeyword && matchStatus;
}));
const variableUsage = computed(() => {
  return (selectedPrompt.value?.variables || []).map((name) => ({
    name,
    used: draft.content.includes(`{${name}}`)
  }));
});
const missingVariables = computed(() => variableUsage.value.filter((item) => !item.used));
const hasChanges = computed(() => {
  const current = selectedPrompt.value;
  if (!current) return false;
  return draft.name !== current.name || draft.scenario !== current.scenario || draft.content !== current.content;
});
const draftDisplayStatus = computed(() => (hasChanges.value ? 'pending' : draft.status));
const canSaveDraft = computed(() => hasChanges.value && !saving.value && Boolean(draft.id));
const canPublish = computed(() => (
  (hasChanges.value || draft.status === 'pending' || selectedPrompt.value?.status === 'pending')
  && !publishing.value
  && Boolean(draft.id)
));
const promptStats = computed(() => ({
  total: prompts.value.length,
  published: prompts.value.filter((item) => promptStatus(item) === 'published').length,
  pending: prompts.value.filter((item) => promptStatus(item) === 'pending').length
}));
const envHasChanges = computed(() => envContent.value !== envOriginalContent.value);

function normalizePrompt(item) {
  return {
    id: item.id,
    promptKey: item.prompt_key,
    name: item.prompt_name,
    agentName: item.agent_name,
    scenario: item.scenario || '',
    status: item.status || 'pending',
    updatedAt: item.updated_at || '',
    variables: item.variables || [],
    content: item.content || ''
  };
}

async function loadPrompts(keepSelection = true) {
  loading.value = true;
  error.value = '';
  try {
    const rows = await fetchSystemPrompts();
    prompts.value = rows.map(normalizePrompt);
    const current = keepSelection
      ? prompts.value.find((item) => item.promptKey === selectedPromptKey.value)
      : null;
    const next = current || prompts.value.find((item) => item.promptKey === 'marketing_report_synthesis') || prompts.value[0];
    if (next) {
      selectPrompt(next);
    } else {
      clearDraft();
    }
  } catch (err) {
    error.value = err.message || '系统提示词加载失败';
  } finally {
    loading.value = false;
  }
}

async function loadEnvConfig() {
  envLoading.value = true;
  envError.value = '';
  try {
    const payload = await fetchEnvConfig();
    envPath.value = payload.env_path || '';
    envRestartRequired.value = Boolean(payload.restart_required);
    envContent.value = payload.content || '';
    envOriginalContent.value = payload.content || '';
  } catch (err) {
    envError.value = err.message || '环境配置加载失败';
  } finally {
    envLoading.value = false;
  }
}

function selectPrompt(prompt) {
  selectedPromptKey.value = prompt.promptKey;
  resetDraft(prompt);
}

function clearDraft() {
  selectedPromptKey.value = '';
  Object.assign(draft, {
    id: null,
    name: '',
    promptKey: '',
    agentName: '',
    scenario: '',
    status: '',
    content: '',
    changeNote: ''
  });
}

function resetDraft(prompt = selectedPrompt.value) {
  if (!prompt) return;
  Object.assign(draft, {
    id: prompt.id,
    name: prompt.name,
    promptKey: prompt.promptKey,
    agentName: prompt.agentName,
    scenario: prompt.scenario,
    status: prompt.status,
    content: prompt.content,
    changeNote: ''
  });
}

function replacePrompt(row) {
  const normalized = normalizePrompt(row);
  const index = prompts.value.findIndex((item) => item.id === normalized.id);
  if (index > -1) {
    prompts.value[index] = normalized;
  } else {
    prompts.value.push(normalized);
  }
  selectPrompt(normalized);
}

async function saveDraft() {
  if (!canSaveDraft.value) return;
  saving.value = true;
  error.value = '';
  try {
    const row = await updateSystemPrompt(draft.id, {
      prompt_name: draft.name,
      agent_name: draft.agentName,
      scenario: draft.scenario,
      content: draft.content,
      variables: selectedPrompt.value?.variables || []
    });
    replacePrompt(row);
  } catch (err) {
    error.value = err.message || '保存草稿失败';
  } finally {
    saving.value = false;
  }
}

async function publishDraft() {
  if (!canPublish.value) return;
  publishing.value = true;
  error.value = '';
  try {
    let promptId = draft.id;
    if (hasChanges.value) {
      const saved = await updateSystemPrompt(draft.id, {
        prompt_name: draft.name,
        agent_name: draft.agentName,
        scenario: draft.scenario,
        content: draft.content,
        variables: selectedPrompt.value?.variables || []
      });
      promptId = saved.id;
      replacePrompt(saved);
    }
    const row = await publishSystemPrompt(promptId, { change_note: draft.changeNote });
    replacePrompt(row);
  } catch (err) {
    error.value = err.message || '发布失败';
  } finally {
    publishing.value = false;
  }
}

async function saveEnvConfig() {
  if (!envHasChanges.value || envSaving.value) return;
  envSaving.value = true;
  envError.value = '';
  try {
    const payload = await updateEnvConfig(envContent.value);
    envPath.value = payload.env_path || '';
    envRestartRequired.value = Boolean(payload.restart_required);
    envContent.value = payload.content || '';
    envOriginalContent.value = payload.content || '';
  } catch (err) {
    envError.value = err.message || '环境配置保存失败';
  } finally {
    envSaving.value = false;
  }
}

function resetEnvConfig() {
  envContent.value = envOriginalContent.value;
}

function openRestartModal() {
  restartMessage.value = '';
  restartModalOpen.value = true;
}

async function confirmRestartBackend() {
  if (restartingBackend.value) return;
  restartingBackend.value = true;
  envError.value = '';
  restartMessage.value = '';
  try {
    const payload = await restartBackend();
    restartMessage.value = payload.message || '后端重启脚本已触发，服务将在数秒后恢复。';
    restartModalOpen.value = false;
  } catch (err) {
    envError.value = err.message || '后端重启失败';
  } finally {
    restartingBackend.value = false;
  }
}

function promptStatus(prompt) {
  if (prompt.promptKey === selectedPromptKey.value && hasChanges.value) {
    return 'pending';
  }
  return prompt.status;
}

function actionHint() {
  if (missingVariables.value.length && (hasChanges.value || draft.status === 'pending')) return '存在缺少变量，请确认后发布';
  if (hasChanges.value) return '当前有未保存修改，可保存草稿或直接发布';
  if (draft.status === 'pending') return '当前为待发布草稿，可直接发布';
  return '修改提示词后可保存或发布';
}

onMounted(() => {
  loadPrompts(false);
  loadEnvConfig();
});
</script>

<template>
  <div class="page settings-page">
    <div class="skph">
      <div>
        <div class="settings-title">系统设置</div>
        <div class="subtitle">上线后可运营维护提示词、模型参数和发布记录</div>
      </div>
      <div class="settings-head-actions">
        <button
          class="btn"
          type="button"
          :disabled="loading || envLoading"
          @click="activeSection === 'envConfig' ? loadEnvConfig() : (activeSection === 'systemPrompt' ? loadPrompts() : undefined)"
        >
          <i class="ti ti-refresh"></i>
          刷新
        </button>
        <button class="btn dbtn" type="button" :disabled="envLoading || envSaving || restartingBackend" @click="openRestartModal">
          <i class="ti ti-refresh-alert"></i>
          {{ restartingBackend ? '重启中...' : '重启后端' }}
        </button>
      </div>
    </div>

    <div class="settings-shell">
      <aside class="settings-nav" aria-label="设置子功能">
        <button
          v-for="section in sections"
          :key="section.key"
          class="settings-nav-item"
          :class="{ active: activeSection === section.key }"
          type="button"
          @click="activeSection = section.key"
        >
          <i class="ti" :class="section.icon"></i>
          <span>
            <strong>{{ section.name }}</strong>
            <small>{{ section.desc }}</small>
          </span>
        </button>
      </aside>

      <section v-if="activeSection === 'systemPrompt'" class="prompt-workbench">
        <div class="prompt-toolbar">
          <div class="prompt-stat">
            <span>全部 {{ promptStats.total }}</span>
            <span>已发布 {{ promptStats.published }}</span>
            <span>待发布 {{ promptStats.pending }}</span>
          </div>
          <div class="prompt-filters">
            <select v-model="statusFilter" class="fsel">
              <option value="all">全部状态</option>
              <option value="published">已发布</option>
              <option value="pending">待发布</option>
            </select>
            <input v-model="keyword" class="fi" placeholder="搜索 prompt key / 提示词名称" />
          </div>
        </div>

        <div v-if="error" class="itip prompt-page-error">
          <i class="ti ti-alert-circle"></i>{{ error }}
        </div>

        <div class="prompt-grid">
          <div class="prompt-list">
            <table class="skt prompt-table">
              <thead>
                <tr>
                  <th>提示词名称</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="loading">
                  <td colspan="2" class="prompt-empty">正在加载系统提示词...</td>
                </tr>
                <tr
                  v-for="prompt in filteredPrompts"
                  v-else
                  :key="prompt.promptKey"
                  :class="{ selected: selectedPromptKey === prompt.promptKey }"
                  @click="selectPrompt(prompt)"
                >
                  <td>
                    <div class="prompt-name">{{ prompt.name }}</div>
                    <div class="prompt-key">{{ prompt.promptKey }} · {{ prompt.agentName }}</div>
                  </td>
                  <td>
                    <span class="tag" :class="promptStatus(prompt) === 'published' ? 'tg' : 'to'">
                      {{ promptStatus(prompt) === 'published' ? '已发布' : '待发布' }}
                    </span>
                  </td>
                </tr>
                <tr v-if="!loading && filteredPrompts.length === 0">
                  <td colspan="2" class="prompt-empty">暂无匹配提示词</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div class="prompt-editor">
            <div class="editor-head">
              <div>
                <div class="editor-title">{{ draft.name || '请选择提示词' }}</div>
                <div class="editor-meta">
                  <span v-if="draft.promptKey">{{ draft.promptKey }}</span>
                  <span v-if="draft.agentName">{{ draft.agentName }}</span>
                </div>
              </div>
              <span v-if="draft.id" class="tag" :class="draftDisplayStatus === 'published' ? 'tg' : 'to'">
                {{ draftDisplayStatus === 'published' ? '已发布' : '待发布' }}
              </span>
            </div>

            <div class="editor-form">
              <div class="frow">
                <div class="fg">
                  <label class="fl">提示词名称</label>
                  <input v-model="draft.name" class="fin" :disabled="!draft.id" />
                </div>
                <div class="fg">
                  <label class="fl">业务场景</label>
                  <input v-model="draft.scenario" class="fin" :disabled="!draft.id" />
                </div>
              </div>

              <div class="variable-bar">
                <div class="variable-title">变量校验</div>
                <span
                  v-for="variable in variableUsage"
                  :key="variable.name"
                  class="variable-chip"
                  :class="{ missing: !variable.used }"
                >
                  {{ variable.name }}
                </span>
                <span v-if="!variableUsage.length" class="variable-empty">暂无变量要求</span>
              </div>

              <textarea v-model="draft.content" class="prompt-textarea" :disabled="!draft.id" spellcheck="false"></textarea>

              <div v-if="missingVariables.length" class="itip prompt-warning">
                <i class="ti ti-alert-circle"></i>
                缺少变量：{{ missingVariables.map((item) => item.name).join('、') }}。请确认后发布。
              </div>
            </div>

            <div class="editor-actions">
              <div class="action-hint" :class="{ active: hasChanges || draft.status === 'pending' }">
                {{ actionHint() }}
              </div>
              <button class="btn" type="button" :disabled="!hasChanges || saving || publishing" @click="resetDraft()">
                <i class="ti ti-restore"></i>
                还原
              </button>
              <button class="btn" type="button" :disabled="!canSaveDraft || publishing" @click="saveDraft">
                <i class="ti ti-device-floppy"></i>
                {{ saving ? '保存中...' : '保存草稿' }}
              </button>
              <button class="btn pri" type="button" :disabled="!canPublish || saving" @click="publishDraft">
                <i class="ti ti-upload"></i>
                {{ publishing ? '发布中...' : '发布生效' }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section v-else-if="activeSection === 'envConfig'" class="env-workbench">
        <div class="env-toolbar">
          <div>
            <div class="env-title">环境配置</div>
            <div class="env-path">{{ envPath || 'backend/.env' }}</div>
          </div>
          <div class="env-actions">
            <button class="btn" type="button" :disabled="envLoading || envSaving" @click="loadEnvConfig">
              <i class="ti ti-refresh"></i>
              重新加载
            </button>
            <button class="btn" type="button" :disabled="!envHasChanges || envSaving" @click="resetEnvConfig">
              <i class="ti ti-restore"></i>
              还原
            </button>
            <button class="btn pri" type="button" :disabled="!envHasChanges || envSaving" @click="saveEnvConfig">
              <i class="ti ti-device-floppy"></i>
              {{ envSaving ? '保存中...' : '保存配置' }}
            </button>
          </div>
        </div>

        <div v-if="envError" class="itip env-page-error">
          <i class="ti ti-alert-circle"></i>{{ envError }}
        </div>
        <div v-if="restartMessage" class="itip env-restart-success">
          <i class="ti ti-circle-check"></i>{{ restartMessage }}
        </div>
        <div v-if="envRestartRequired" class="itip env-restart-tip">
          <i class="ti ti-alert-triangle"></i>
          已保存包含需重启的配置项，请重启后端服务后完全生效。
        </div>

        <div class="env-scroll">
          <div v-if="envLoading" class="env-empty">正在加载环境配置...</div>
          <textarea
            v-else
            v-model="envContent"
            class="env-rich-editor"
            placeholder="KEY=value"
            spellcheck="false"
          ></textarea>
        </div>
      </section>

      <section v-else-if="activeSection === 'quickPrompt'" class="quick-prompt-workbench">
        <QuickPromptManager />
      </section>

      <section v-else class="settings-placeholder">
        <i class="ti ti-tool"></i>
        <strong>{{ sections.find((item) => item.key === activeSection)?.name }}</strong>
        <span>该子功能预留给后续配置项。</span>
      </section>
    </div>

    <ModalDialog
      :open="restartModalOpen"
      title="确认重启后端"
      :danger="true"
      :close-on-backdrop="!restartingBackend"
      @close="!restartingBackend && (restartModalOpen = false)"
    >
      <p class="restart-confirm-text">
        确认要重启后端系统吗？系统将调用后端配置的重启脚本或命令，重启期间服务会短暂不可用，正在执行的任务可能会中断。
      </p>
      <p class="restart-confirm-sub">
        建议在保存配置后、没有运行中任务时执行重启。
      </p>
      <template #footer>
        <button class="btn" type="button" :disabled="restartingBackend" @click="restartModalOpen = false">取消</button>
        <button class="btn dbtn" type="button" :disabled="restartingBackend" @click="confirmRestartBackend">
          <i class="ti ti-refresh-alert"></i>
          {{ restartingBackend ? '正在重启...' : '确认重启' }}
        </button>
      </template>
    </ModalDialog>
  </div>
</template>

<style scoped>
.settings-page { background: var(--bg); }
.settings-title { font-size: 15px; font-weight: 600; color: var(--t1); }
.settings-head-actions { display: flex; align-items: center; gap: 8px; }
.settings-shell { flex: 1; min-height: 0; display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 0; overflow: hidden; }
.settings-nav { background: #fff; border-right: 1px solid var(--border); padding: 14px 12px; overflow-y: auto; }
.settings-nav-item { width: 100%; display: flex; align-items: center; gap: 10px; padding: 10px; border: 1px solid transparent; border-radius: var(--radius-sm); background: transparent; cursor: pointer; text-align: left; color: var(--t2); margin-bottom: 6px; }
.settings-nav-item i { font-size: 18px; color: var(--t3); }
.settings-nav-item strong { display: block; font-size: 13px; color: var(--t1); margin-bottom: 2px; }
.settings-nav-item small { display: block; font-size: 11px; color: var(--t3); }
.settings-nav-item:hover, .settings-nav-item.active { background: var(--pl); border-color: var(--color-primary-border); }
.settings-nav-item.active i, .settings-nav-item.active strong { color: var(--primary); }
.prompt-workbench { min-width: 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.prompt-toolbar { background: #fff; border-bottom: 1px solid var(--border); padding: 10px 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.prompt-stat { display: flex; gap: 10px; color: var(--t2); font-size: 12px; }
.prompt-stat span { padding: 3px 8px; background: var(--bg-subtle); border: 1px solid var(--border); border-radius: var(--radius-xs); }
.prompt-filters { display: flex; align-items: center; gap: 8px; min-width: min(100%, 440px); }
.prompt-filters .fsel { width: 120px; flex-shrink: 0; }
.prompt-page-error { margin: 10px 16px 0; border-color: var(--color-danger-border); background: var(--color-danger-weak); color: var(--danger); }
.prompt-grid { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(360px, 42%) minmax(420px, 1fr); overflow: hidden; }
.prompt-list { min-width: 0; overflow: auto; padding: 14px 12px 16px 16px; }
.prompt-table th, .prompt-table td { padding: 11px 12px; }
.prompt-table tr { cursor: pointer; }
.prompt-table tr.selected td { background: var(--color-primary-weak); }
.prompt-name { font-size: 12px; font-weight: 600; color: var(--t1); margin-bottom: 3px; }
.prompt-key { font-size: 11px; color: var(--t3); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.prompt-empty { text-align: center; color: var(--t3); }
.prompt-editor { min-width: 0; min-height: 0; background: #fff; border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
.editor-head { min-height: 64px; border-bottom: 1px solid var(--border); padding: 12px 16px; display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.editor-title { font-size: 14px; font-weight: 600; color: var(--t1); margin-bottom: 5px; }
.editor-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 11px; color: var(--t3); }
.editor-meta span { padding: 2px 6px; border: 1px solid var(--border); border-radius: var(--radius-xs); background: var(--bg-subtle); }
.editor-form { flex: 1; min-height: 0; overflow: auto; padding: 14px 16px; }
.variable-bar { border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-subtle); padding: 9px 10px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.variable-title { font-size: 12px; color: var(--t2); font-weight: 600; margin-right: 4px; }
.variable-chip { font-size: 11px; color: var(--color-primary); background: var(--color-primary-weak); border: 1px solid var(--color-primary-border); border-radius: var(--radius-pill); padding: 2px 8px; }
.variable-chip.missing { color: var(--color-warning); background: var(--color-warning-weak); border-color: var(--color-warning-border); }
.variable-empty { font-size: 11px; color: var(--t3); }
.prompt-textarea { width: 100%; min-height: 420px; resize: vertical; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px; outline: none; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; line-height: 1.7; color: var(--t1); background: #fff; }
.prompt-textarea:focus { border-color: var(--primary); box-shadow: var(--shadow-focus); }
.prompt-warning { margin: 10px 0 0; border-color: var(--color-warning-border); background: var(--color-warning-weak); color: var(--color-warning); }
.editor-actions { border-top: 1px solid var(--border); padding: 12px 16px; display: flex; align-items: center; justify-content: flex-end; gap: 8px; background: #fff; }
.action-hint { margin-right: auto; color: var(--t3); font-size: 12px; line-height: 1.5; }
.action-hint.active { color: var(--primary); }
.env-workbench { min-width: 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.quick-prompt-workbench { min-width: 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.env-toolbar { background: #fff; border-bottom: 1px solid var(--border); padding: 12px 16px; display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.env-title { font-size: 14px; font-weight: 600; color: var(--t1); margin-bottom: 4px; }
.env-path { max-width: min(68vw, 760px); color: var(--t3); font-size: 11px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.env-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.env-page-error { margin: 10px 16px 0; border-color: var(--color-danger-border); background: var(--color-danger-weak); color: var(--danger); }
.env-restart-tip { margin: 10px 16px 0; border-color: var(--color-warning-border); background: var(--color-warning-weak); color: var(--color-warning); }
.env-restart-success { margin: 10px 16px 0; border-color: var(--color-success-border); background: var(--color-success-weak); color: var(--color-success); }
.env-scroll { flex: 1; min-height: 0; overflow: hidden; padding: 14px 16px 18px; display: flex; }
.env-rich-editor { width: 100%; min-height: 0; flex: 1; resize: none; border: 1px solid var(--border); border-radius: var(--radius-sm); background: #fff; color: var(--t1); outline: none; padding: 14px; font-size: 12px; line-height: 1.65; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre; overflow: auto; }
.env-rich-editor:focus { border-color: var(--primary); box-shadow: var(--shadow-focus); }
.env-empty { min-height: 180px; display: flex; align-items: center; justify-content: center; color: var(--t3); font-size: 13px; }
.settings-placeholder { margin: 16px; background: #fff; border: 1px solid var(--border); border-radius: var(--radius-sm); min-height: 220px; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 8px; color: var(--t3); }
.settings-placeholder i { font-size: 28px; color: var(--primary); }
.settings-placeholder strong { color: var(--t1); font-size: 14px; }
.restart-confirm-text { margin: 0; color: var(--t1); line-height: 1.7; }
.restart-confirm-sub { margin: 8px 0 0; color: var(--t3); font-size: 12px; line-height: 1.6; }
@media (max-width: 1100px) {
  .settings-shell { grid-template-columns: 180px minmax(0, 1fr); }
  .prompt-grid { grid-template-columns: 1fr; overflow: auto; }
  .prompt-list, .prompt-editor { overflow: visible; }
  .prompt-editor { border-left: 0; border-top: 1px solid var(--border); }
}
@media (max-width: 760px) {
  .settings-shell { display: flex; flex-direction: column; overflow: auto; }
  .settings-nav { display: flex; gap: 8px; border-right: 0; border-bottom: 1px solid var(--border); overflow-x: auto; }
  .settings-nav-item { min-width: 160px; margin-bottom: 0; }
  .prompt-filters { flex-wrap: wrap; min-width: 0; width: 100%; }
  .prompt-filters .fsel, .prompt-filters .fi { width: 100%; }
  .frow { flex-direction: column; }
  .env-toolbar { align-items: flex-start; flex-direction: column; }
  .env-path { max-width: 100%; white-space: normal; }
  .env-actions { width: 100%; justify-content: flex-start; }
}
</style>

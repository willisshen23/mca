<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { fetchLogFiles, fetchLogContent, downloadLogFile, tailLog } from '../api/logs.js';
import TopBar from '../components/layout/TopBar.vue';

const logFiles = ref([]);
const selectedFile = ref('');
const logContent = ref('');
const loading = ref(false);
const error = ref('');
const lines = ref(200);
const tailMode = ref(true);
const autoRefresh = ref(false);
let refreshTimer = null;

async function loadFiles() {
  try {
    const data = await fetchLogFiles();
    logFiles.value = data.files || [];
    if (logFiles.value.length > 0 && !selectedFile.value) {
      selectedFile.value = logFiles.value[0].name;
      await loadContent();
    }
  } catch (err) {
    error.value = err.message || '加载日志文件列表失败';
  }
}

async function loadContent() {
  if (!selectedFile.value) return;
  loading.value = true;
  error.value = '';
  try {
    logContent.value = await fetchLogContent({
      filename: selectedFile.value,
      lines: lines.value,
      tail: tailMode.value,
    });
  } catch (err) {
    error.value = err.message || '加载日志内容失败';
  } finally {
    loading.value = false;
  }
}

async function loadTail() {
  loading.value = true;
  error.value = '';
  try {
    logContent.value = await tailLog({
      lines: lines.value,
      filename: selectedFile.value || undefined,
    });
  } catch (err) {
    error.value = err.message || '获取最新日志失败';
  } finally {
    loading.value = false;
  }
}

function handleDownload() {
  if (!selectedFile.value) return;
  downloadLogFile(selectedFile.value);
}

function toggleAutoRefresh() {
  if (autoRefresh.value) {
    refreshTimer = setInterval(loadTail, 3000);
  } else {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }
}

watch(autoRefresh, toggleAutoRefresh);
watch(selectedFile, loadContent);

onMounted(() => {
  loadFiles();
});
</script>

<template>
  <div class="page logs-page">
    <TopBar title="系统日志">
      <button class="btn" type="button" :disabled="loading" @click="loadFiles">
        <i class="ti ti-refresh"></i>
        刷新列表
      </button>
      <button class="btn" type="button" :disabled="loading || !selectedFile" @click="handleDownload">
        <i class="ti ti-download"></i>
        下载日志
      </button>
    </TopBar>

    <div class="content">
      <section class="sc logs-section">
        <div class="logs-head">
          <div class="logs-title">
            <i class="ti ti-file-text"></i>
            <span class="stitle">系统运行日志</span>
          </div>
          <span class="logs-count">共 {{ logFiles.length }} 个日志文件</span>
        </div>

        <div class="logs-toolbar">
          <select v-model="selectedFile" class="logs-select" :disabled="loading">
            <option value="">选择日志文件</option>
            <option v-for="file in logFiles" :key="file.name" :value="file.name">
              {{ file.name }} ({{ (file.size / 1024).toFixed(1) }} KB)
            </option>
          </select>
          <select v-model.number="lines" class="logs-select" @change="loadContent">
            <option :value="50">50 行</option>
            <option :value="100">100 行</option>
            <option :value="200">200 行</option>
            <option :value="500">500 行</option>
            <option :value="1000">1000 行</option>
          </select>
          <label class="logs-checkbox">
            <input type="checkbox" v-model="tailMode" @change="loadContent" />
            <span>从尾部读取</span>
          </label>
          <label class="logs-checkbox">
            <input type="checkbox" v-model="autoRefresh" />
            <span>自动刷新 (3s)</span>
          </label>
          <button class="btn pri" type="button" :disabled="loading" @click="loadTail">
            <i class="ti ti-eye"></i>
            查看最新
          </button>
        </div>

        <div v-if="error" class="itip logs-error">
          <i class="ti ti-alert-circle"></i>{{ error }}
        </div>

        <div class="logs-content">
          <div v-if="loading" class="logs-loading">正在加载日志...</div>
          <div v-else-if="!logContent" class="logs-empty">
            <i class="ti ti-file-text"></i>
            <span>选择日志文件查看内容</span>
          </div>
          <pre v-else class="logs-pre">{{ logContent }}</pre>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.logs-page { background: var(--bg); }
.logs-section { min-width: 0; }
.logs-head { justify-content: space-between; margin-bottom: 12px; }
.logs-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.logs-count { font-size: 12px; color: var(--t3); }
.logs-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.logs-select { height: 32px; border: 1px solid var(--border); border-radius: var(--radius-xs); background: #fff; color: var(--t1); padding: 0 10px; outline: none; min-width: 200px; }
.logs-checkbox { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--t2); cursor: pointer; }
.logs-checkbox input { accent-color: var(--primary); }
.logs-error { border-color: var(--color-danger-border); background: var(--color-danger-weak); color: var(--danger); }
.logs-content { background: #0d1117; border-radius: var(--radius-md); overflow: hidden; }
.logs-loading, .logs-empty { min-height: 300px; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #8b949e; gap: 12px; }
.logs-loading { font-size: 14px; }
.logs-empty i { font-size: 36px; opacity: 0.5; }
.logs-empty span { font-size: 13px; }
.logs-pre { margin: 0; padding: 16px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; line-height: 1.6; color: var(--border-strong); white-space: pre-wrap; word-break: break-all; max-height: calc(100vh - 280px); overflow-y: auto; }
.logs-pre::-webkit-scrollbar { width: 8px; }
.logs-pre::-webkit-scrollbar-track { background: #161b22; }
.logs-pre::-webkit-scrollbar-thumb { background: #30363d; border-radius: var(--radius-xs); }
.logs-pre::-webkit-scrollbar-thumb:hover { background: var(--text-2); }
</style>
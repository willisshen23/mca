<script setup>
import { computed, onMounted, ref } from 'vue';
import { fetchConversationLogs, fetchThreadTurns } from '../api/conversationLogs';
import ModalDialog from '../components/common/ModalDialog.vue';
import TopBar from '../components/layout/TopBar.vue';

const logs = ref([]);
const loading = ref(false);
const error = ref('');
const detailOpen = ref(false);
const detailLoading = ref(false);
const detailThreadId = ref('');
const detailTurns = ref([]);

const keyword = ref('');
const userIdFilter = ref('');
const statusFilter = ref('');
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));

async function loadLogs() {
  loading.value = true;
  error.value = '';
  try {
    const data = await fetchConversationLogs({
      keyword: keyword.value.trim(),
      userId: userIdFilter.value.trim(),
      status: statusFilter.value,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value
    });
    logs.value = data.items || [];
    total.value = data.total || 0;
    if (page.value > totalPages.value) {
      page.value = totalPages.value;
      await loadLogs();
    }
  } catch (err) {
    error.value = err.message || '对话记录加载失败';
  } finally {
    loading.value = false;
  }
}

async function openDetail(row) {
  detailOpen.value = true;
  detailLoading.value = true;
  detailThreadId.value = row.thread_id;
  detailTurns.value = [];
  try {
    const data = await fetchThreadTurns(row.thread_id);
    detailTurns.value = data.turns || [];
  } catch (err) {
    error.value = err.message || '会话详情加载失败';
  } finally {
    detailLoading.value = false;
  }
}

function formatTime(value) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (num) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function formatDuration(value) {
  const duration = Number(value);
  if (!Number.isFinite(duration) || duration <= 0) return '-';
  if (duration < 1000) return `${duration}ms`;
  return `${(duration / 1000).toFixed(1)}s`;
}

function statusText(status) {
  if (status === 'success') return '成功';
  if (status === 'failed') return '失败';
  if (status === 'cancelled') return '已取消';
  if (status === 'running') return '运行中';
  return status || '-';
}

function statusClass(status) {
  if (status === 'success') return 'tg';
  if (status === 'failed') return 'tdanger';
  if (status === 'running') return 'tb';
  return 'tgr';
}

function principal(row) {
  return row.user_name || row.user_id || '-';
}

function searchLogs() {
  page.value = 1;
  loadLogs();
}

function resetSearch() {
  keyword.value = '';
  userIdFilter.value = '';
  statusFilter.value = '';
  page.value = 1;
  loadLogs();
}

function changePage(nextPage) {
  if (nextPage < 1 || nextPage > totalPages.value || nextPage === page.value) return;
  page.value = nextPage;
  loadLogs();
}

function changePageSize() {
  page.value = 1;
  loadLogs();
}

onMounted(loadLogs);
</script>

<template>
  <div class="page logs-page">
    <TopBar title="对话记录">
      <button class="btn" type="button" :disabled="loading" @click="loadLogs">
        <i class="ti ti-refresh"></i>
        刷新
      </button>
    </TopBar>

    <div class="content">
      <section class="sc logs-section">
        <div class="sh logs-head">
          <div class="logs-title">
            <i class="ti ti-messages"></i>
            <span class="stitle">用户对话记录</span>
          </div>
          <span class="logs-count">共 {{ total }} 条</span>
        </div>

        <div class="logs-filter">
          <input
            v-model="userIdFilter"
            class="fi filter-input"
            placeholder="按用户ID查询"
            @keydown.enter="searchLogs"
          />
          <input
            v-model="keyword"
            class="fi filter-input"
            placeholder="按关键词/提问内容查询"
            @keydown.enter="searchLogs"
          />
          <select v-model="statusFilter" class="fi status-select" @change="searchLogs">
            <option value="">全部状态</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
            <option value="cancelled">已取消</option>
            <option value="running">运行中</option>
          </select>
          <button class="btn pri" type="button" :disabled="loading" @click="searchLogs">
            <i class="ti ti-search"></i>
            查询
          </button>
          <button class="btn" type="button" :disabled="loading" @click="resetSearch">
            <i class="ti ti-restore"></i>
            重置
          </button>
        </div>

        <div v-if="error" class="itip logs-error">
          <i class="ti ti-alert-circle"></i>{{ error }}
        </div>

        <div class="table-scroll">
          <table class="tbl logs-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>发起人</th>
                <th>会话</th>
                <th>用户提问</th>
                <th>回复摘要</th>
                <th>状态</th>
                <th>耗时</th>
                <th>查看</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="8" class="logs-empty">正在加载对话记录...</td>
              </tr>
              <tr v-else-if="logs.length === 0">
                <td colspan="8" class="logs-empty">暂无对话记录</td>
              </tr>
              <tr v-for="row in logs" v-else :key="row.id">
                <td class="logs-time">{{ formatTime(row.started_at) }}</td>
                <td class="principal" :title="principal(row)">{{ principal(row) }}</td>
                <td>
                  <span class="thread-id" :title="row.thread_id">{{ row.thread_id }}</span>
                </td>
                <td>
                  <span class="question" :title="row.user_text">{{ row.user_text || '-' }}</span>
                </td>
                <td>
                  <span class="answer" :title="row.response_summary">{{ row.response_summary || '-' }}</span>
                </td>
                <td>
                  <span class="tag" :class="statusClass(row.status)">{{ statusText(row.status) }}</span>
                </td>
                <td>{{ formatDuration(row.duration_ms) }}</td>
                <td>
                  <button class="btn sm" type="button" @click="openDetail(row)">查看</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="logs-pagination">
          <span>共 {{ total }} 条</span>
          <select v-model.number="pageSize" class="page-size" :disabled="loading" @change="changePageSize">
            <option :value="10">10 条/页</option>
            <option :value="20">20 条/页</option>
            <option :value="50">50 条/页</option>
            <option :value="100">100 条/页</option>
          </select>
          <button class="pgb" type="button" :disabled="page <= 1 || loading" @click="changePage(page - 1)">
            <i class="ti ti-chevron-left"></i>
          </button>
          <span class="page-current">{{ page }} / {{ totalPages }}</span>
          <button class="pgb" type="button" :disabled="page >= totalPages || loading" @click="changePage(page + 1)">
            <i class="ti ti-chevron-right"></i>
          </button>
        </div>
      </section>
    </div>

    <ModalDialog
      :open="detailOpen"
      :large="true"
      :title="`完整对话记录 - ${detailThreadId}`"
      @close="detailOpen = false"
    >
      <div v-if="detailLoading" class="detail-loading">正在加载完整对话记录...</div>
      <div v-else-if="detailTurns.length === 0" class="detail-loading">该会话暂无对话记录</div>
      <div v-else class="conversation">
        <div v-for="turn in detailTurns" :key="turn.id" class="turn">
          <div class="turn-meta">
            <span class="turn-time">{{ formatTime(turn.started_at) }}</span>
            <span class="tag" :class="statusClass(turn.status)">{{ statusText(turn.status) }}</span>
            <span class="turn-dur">{{ formatDuration(turn.duration_ms) }}</span>
          </div>
          <div class="bubble user">
            <div class="bubble-role"><i class="ti ti-user"></i> 用户</div>
            <div class="bubble-text">{{ turn.user_text || '（空）' }}</div>
          </div>
          <div class="bubble ai">
            <div class="bubble-role"><i class="ti ti-robot"></i> 智能体</div>
            <div class="bubble-text">
              {{ turn.assistant_response || (turn.failure_reason ? `（失败：${turn.failure_reason}）` : '（无回复）') }}
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <button class="btn" type="button" @click="detailOpen = false">关闭</button>
      </template>
    </ModalDialog>
  </div>
</template>

<style scoped>
.logs-page { background: var(--bg); }
.logs-section { min-width: 0; }
.logs-head { justify-content: space-between; }
.logs-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.logs-count { font-size: 12px; color: var(--t3); }
.logs-filter { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.filter-input { width: min(260px, 100%); flex: 0 1 260px; }
.status-select { width: 130px; }
.logs-error { border-color: #ffd0d0; background: #fff5f5; color: var(--danger); }
.logs-table th, .logs-table td { white-space: nowrap; }
.logs-time { color: var(--t2); }
.thread-id { display: inline-block; max-width: 140px; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.principal { max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
.question, .answer { display: inline-block; max-width: 280px; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; white-space: nowrap; }
.logs-empty { text-align: center; color: var(--t3); padding: 28px 12px !important; }
.tdanger { background: #FFF0F0; color: var(--danger); }
.logs-pagination { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding-top: 12px; color: var(--t2); font-size: 12px; flex-wrap: wrap; }
.page-size { height: 28px; border: 1px solid var(--border); border-radius: 4px; background: #fff; color: var(--t1); padding: 0 8px; outline: none; }
.page-current { min-width: 52px; text-align: center; color: var(--t2); }
.pgb:disabled { cursor: not-allowed; opacity: .45; pointer-events: none; }
.detail-loading { min-height: 200px; display: flex; align-items: center; justify-content: center; color: var(--t3); }
.conversation { max-height: 60vh; overflow: auto; display: flex; flex-direction: column; gap: 18px; padding: 4px; }
.turn { display: flex; flex-direction: column; gap: 8px; border-bottom: 1px dashed var(--border); padding-bottom: 14px; }
.turn:last-child { border-bottom: 0; }
.turn-meta { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--t3); }
.bubble { border-radius: 8px; padding: 10px 12px; }
.bubble.user { background: #EEF3FF; }
.bubble.ai { background: #F7F8FA; }
.bubble-role { font-size: 12px; color: var(--t2); margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.bubble-text { font-size: 13px; line-height: 1.7; color: var(--t1); white-space: pre-wrap; word-break: break-word; }
:deep(.modal.lg) { width: min(960px, 96vw); }
:deep(.modal.lg .mb) { max-height: 74vh; overflow: hidden; }
@media (max-width: 760px) {
  .question, .answer { max-width: 160px; }
  .thread-id { max-width: 100px; }
}
</style>

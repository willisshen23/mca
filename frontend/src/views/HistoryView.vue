<script setup>
import { computed, onMounted, ref } from 'vue';
import {
  exportHistorySessionsUrl,
  fetchHistorySessionDetail,
  fetchHistorySessions,
  fetchRunHistoryDetail,
  reportDownloadUrl
} from '../api/agentRunHistory';
import ModalDialog from '../components/common/ModalDialog.vue';
import TopBar from '../components/layout/TopBar.vue';

const sessions = ref([]);
const loading = ref(false);
const error = ref('');
const keyword = ref('');
const feedbackFilter = ref('');
const dateFrom = ref('');
const dateTo = ref('');
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));

const sessionOpen = ref(false);
const sessionLoading = ref(false);
const sessionDetail = ref(null);

const detailOpen = ref(false);
const detailLoading = ref(false);
const selectedDetail = ref(null);
const copied = ref(false);

async function loadSessions() {
  loading.value = true;
  error.value = '';
  try {
    const data = await fetchHistorySessions({
      keyword: keyword.value.trim(),
      feedback: feedbackFilter.value,
      dateFrom: dateFrom.value,
      dateTo: dateTo.value,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value
    });
    sessions.value = data.items || [];
    total.value = data.total || 0;
    if (page.value > totalPages.value) {
      page.value = totalPages.value;
      await loadSessions();
    }
  } catch (err) {
    error.value = err.message || '会话历史加载失败';
  } finally {
    loading.value = false;
  }
}

async function openSession(row) {
  sessionOpen.value = true;
  sessionLoading.value = true;
  sessionDetail.value = null;
  try {
    const data = await fetchHistorySessionDetail(row.thread_id);
    data.reports = (data.reports || []).map((report) => ({ ...report, expanded: false }));
    sessionDetail.value = data;
  } catch (err) {
    error.value = err.message || '会话详情加载失败';
    sessionOpen.value = false;
  } finally {
    sessionLoading.value = false;
  }
}

function toggleReport(report) {
  report.expanded = !report.expanded;
}

async function openPromptDetail(report) {
  detailOpen.value = true;
  detailLoading.value = true;
  selectedDetail.value = { ...report, prompt_text: '' };
  try {
    selectedDetail.value = await fetchRunHistoryDetail(report.id);
  } catch (err) {
    selectedDetail.value = { ...report, prompt_text: `提示词加载失败：${err.message || '未知错误'}` };
  } finally {
    detailLoading.value = false;
  }
}

async function copyPrompt() {
  const text = selectedDetail.value?.prompt_text || '';
  if (!text) return;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      // 非安全上下文（如 HTTP）下的降级方案
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      textarea.setAttribute('readonly', '');
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  } catch (err) {
    error.value = '复制失败，请手动复制';
  }
}

function downloadVersion(report, version, format = 'html') {
  window.location.href = reportDownloadUrl(report.id, format, version.version_no);
}

function sortedVersions(report) {
  return [...(report.versions || [])].sort((a, b) => (a.version_no || 0) - (b.version_no || 0));
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

function feedbackText(feedback) {
  if (feedback === 'like') return '已点赞';
  if (feedback === 'dislike') return '已点踩';
  return '未反馈';
}

function feedbackClass(feedback) {
  if (feedback === 'like') return 'feedback-like';
  if (feedback === 'dislike') return 'feedback-dislike';
  return 'feedback-empty';
}

function sourceText(source) {
  if (source === 'modify') return '修改';
  return '生成';
}

function sourceClass(source) {
  return source === 'modify' ? 'source-modify' : 'source-generate';
}

function activityTemplateName(row) {
  return row?.activity_template_snapshot?.name || '-';
}

function principal(row) {
  return row?.user_name || row?.user_id || '-';
}

function searchSessions() {
  page.value = 1;
  loadSessions();
}

function resetSearch() {
  keyword.value = '';
  feedbackFilter.value = '';
  dateFrom.value = '';
  dateTo.value = '';
  page.value = 1;
  loadSessions();
}

function exportSessions() {
  const url = exportHistorySessionsUrl({
    keyword: keyword.value.trim(),
    feedback: feedbackFilter.value,
    dateFrom: dateFrom.value,
    dateTo: dateTo.value
  });
  window.location.href = url;
}

function changePage(nextPage) {
  if (nextPage < 1 || nextPage > totalPages.value || nextPage === page.value) return;
  page.value = nextPage;
  loadSessions();
}

function changePageSize() {
  page.value = 1;
  loadSessions();
}

onMounted(loadSessions);
</script>

<template>
  <div class="page history-page">
    <TopBar title="运行历史">
      <button class="btn" type="button" :disabled="loading" @click="loadSessions">
        <i class="ti ti-refresh"></i>
        刷新
      </button>
    </TopBar>

    <div class="content">
      <section class="sc history-section">
        <div class="sh history-head">
          <div class="history-title">
            <i class="ti ti-history"></i>
            <span class="stitle">会话报告历史</span>
          </div>
          <span class="history-count">共 {{ total }} 个会话</span>
        </div>

        <div class="history-filter">
          <input
            v-model="keyword"
            class="fi keyword-filter-input"
            placeholder="会话标题 / 发起人 / request_id / 提问"
            @keydown.enter="searchSessions"
          />
          <select v-model="feedbackFilter" class="fi feedback-filter-select" @change="searchSessions">
            <option value="">全部反馈</option>
            <option value="like">有点赞</option>
            <option value="dislike">有点踩</option>
            <option value="none">未反馈</option>
          </select>
          <input v-model="dateFrom" class="fi date-filter-input" type="date" title="开始日期" @change="searchSessions" />
          <span class="date-sep">至</span>
          <input v-model="dateTo" class="fi date-filter-input" type="date" title="结束日期" @change="searchSessions" />
          <button class="btn pri" type="button" :disabled="loading" @click="searchSessions">
            <i class="ti ti-search"></i>
            查询
          </button>
          <button class="btn" type="button" :disabled="loading || (!keyword && !feedbackFilter && !dateFrom && !dateTo)" @click="resetSearch">
            <i class="ti ti-restore"></i>
            重置
          </button>
          <button class="btn" type="button" @click="exportSessions">
            <i class="ti ti-file-export"></i>
            导出 Excel
          </button>
        </div>

        <div v-if="error" class="itip history-error">
          <i class="ti ti-alert-circle"></i>{{ error }}
        </div>

        <div class="table-scroll">
          <table class="tbl history-table">
            <thead>
              <tr>
                <th>最后活跃时间</th>
                <th>会话标题</th>
                <th>发起人</th>
                <th class="num">报告数</th>
                <th class="num">版本数</th>
                <th class="num"><i class="ti ti-thumb-up" aria-hidden="true"></i></th>
                <th class="num"><i class="ti ti-thumb-down" aria-hidden="true"></i></th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="8" class="history-empty">正在加载会话历史...</td>
              </tr>
              <tr v-else-if="sessions.length === 0">
                <td colspan="8" class="history-empty">暂无会话历史</td>
              </tr>
              <tr v-for="row in sessions" v-else :key="row.thread_id">
                <td class="history-time">{{ formatTime(row.last_active_at) }}</td>
                <td>
                  <span class="question" :title="row.title">{{ row.title || '-' }}</span>
                </td>
                <td class="principal" :title="principal(row)">{{ principal(row) }}</td>
                <td class="num">{{ row.report_count ?? 0 }}</td>
                <td class="num">{{ row.version_count ?? 0 }}</td>
                <td class="num">
                  <span class="count-like" v-if="row.like_count">{{ row.like_count }}</span>
                  <span v-else class="count-empty">0</span>
                </td>
                <td class="num">
                  <span class="count-dislike" v-if="row.dislike_count">{{ row.dislike_count }}</span>
                  <span v-else class="count-empty">0</span>
                </td>
                <td>
                  <button class="btn sm" type="button" @click="openSession(row)">查看</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="history-pagination">
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
      :open="sessionOpen"
      :large="true"
      :title="`会话详情 - ${sessionDetail?.title || ''}`"
      @close="sessionOpen = false"
    >
      <div v-if="sessionLoading" class="prompt-loading">正在加载会话详情...</div>
      <div v-else-if="sessionDetail" class="session-content">
        <div class="session-summary">
          <span class="session-meta">发起人：{{ principal(sessionDetail) }}</span>
          <span class="session-meta">报告 {{ sessionDetail.report_count ?? (sessionDetail.reports || []).length }} 份</span>
          <span class="session-meta">版本 {{ sessionDetail.version_count ?? 0 }} 个</span>
          <span class="session-meta count-like"><i class="ti ti-thumb-up" aria-hidden="true"></i> {{ sessionDetail.like_count ?? 0 }}</span>
          <span class="session-meta count-dislike"><i class="ti ti-thumb-down" aria-hidden="true"></i> {{ sessionDetail.dislike_count ?? 0 }}</span>
        </div>

        <table class="tbl report-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>request_id</th>
              <th>提问摘要</th>
              <th>分析模板</th>
              <th>状态</th>
              <th>耗时</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="(sessionDetail.reports || []).length === 0">
              <td colspan="7" class="history-empty">该会话暂无报告记录</td>
            </tr>
            <template v-for="report in sessionDetail.reports" v-else :key="report.request_id || report.id">
              <tr>
                <td class="history-time">{{ formatTime(report.started_at) }}</td>
                <td>
                  <span class="request-id" :title="report.request_id">{{ report.request_id }}</span>
                </td>
                <td>
                  <span class="question-sm" :title="report.user_text">{{ report.user_text || '-' }}</span>
                </td>
                <td>
                  <span class="template-name" :title="activityTemplateName(report)">{{ activityTemplateName(report) }}</span>
                </td>
                <td>
                  <span class="tag" :class="statusClass(report.status)">{{ statusText(report.status) }}</span>
                </td>
                <td>{{ formatDuration(report.duration_ms) }}</td>
                <td>
                  <span class="report-actions">
                    <button class="report-link" type="button" @click="toggleReport(report)">
                      {{ report.expanded ? '收起' : `版本(${(report.versions || []).length || report.latest_version_no || 0})` }}
                    </button>
                    <button class="report-link" type="button" @click="openPromptDetail(report)">查看</button>
                  </span>
                </td>
              </tr>
              <tr v-if="report.expanded" class="version-row">
                <td colspan="7">
                  <div v-if="(report.versions || []).length === 0" class="version-empty">暂无版本记录</div>
                  <div v-for="version in sortedVersions(report)" v-else :key="version.version_id || version.version_no" class="version-item">
                    <div class="version-line">
                      <span class="version-badge">v{{ version.version_no }}</span>
                      <span class="source-tag" :class="sourceClass(version.source)">{{ sourceText(version.source) }}</span>
                      <span class="version-note" :title="version.change_note || ''">{{ version.change_note || '-' }}</span>
                      <span class="version-time">{{ formatTime(version.created_at) }}</span>
                      <span class="feedback-tag" :class="feedbackClass(version.feedback)">
                        <i
                          v-if="version.feedback"
                          class="ti"
                          :class="version.feedback === 'like' ? 'ti-thumb-up' : 'ti-thumb-down'"
                          aria-hidden="true"
                        ></i>
                        {{ feedbackText(version.feedback) }}
                      </span>
                      <span v-if="version.feedback" class="version-feedback-meta">
                        {{ version.feedback_user_id || '-' }} · {{ formatTime(version.feedback_at) }}
                      </span>
                      <span class="report-actions">
                        <button class="report-link" type="button" @click="downloadVersion(report, version, 'html')">HTML</button>
                      </span>
                    </div>
                    <div v-if="version.feedback === 'dislike' && version.feedback_comment" class="version-comment">
                      点踩原因：{{ version.feedback_comment }}
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <template #footer>
        <button class="btn" type="button" @click="sessionOpen = false">关闭</button>
      </template>
    </ModalDialog>

    <ModalDialog
      :open="detailOpen"
      :large="true"
      :title="`运行详情 - ${selectedDetail?.request_id || ''}`"
      @close="detailOpen = false; copied = false"
    >
      <div v-if="detailLoading" class="prompt-loading">正在加载运行详情...</div>
      <div v-else class="detail-content">
        <section class="detail-section">
          <h4 class="detail-section-title">匹配模板信息</h4>
          <div class="detail-grid">
            <div class="detail-item">
              <span class="detail-label">分析模板名称</span>
              <span class="detail-value">{{ selectedDetail?.activity_template_snapshot?.name || '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">分析模板类型</span>
              <span class="detail-value">{{ selectedDetail?.activity_template_snapshot?.type || '-' }}</span>
            </div>
            <div class="detail-item detail-item-wide">
              <span class="detail-label">分析模板描述</span>
              <span class="detail-value">{{ selectedDetail?.activity_template_snapshot?.description || '-' }}</span>
            </div>
            <div class="detail-item">
              <span class="detail-label">匹配的数据模板</span>
              <span class="detail-value">{{ selectedDetail?.matched_data_template_name || '-' }}</span>
            </div>
          </div>
        </section>
        <section class="detail-section">
          <h4 class="detail-section-title">完整提示词</h4>
          <textarea
            class="prompt-viewer"
            readonly
            spellcheck="false"
            :value="selectedDetail?.prompt_text || '本次运行暂无提示词记录'"
          ></textarea>
        </section>
      </div>
      <template #footer>
        <button class="btn" type="button" @click="detailOpen = false">关闭</button>
        <button class="btn pri" type="button" :disabled="!selectedDetail?.prompt_text" @click="copyPrompt">
          <i class="ti" :class="copied ? 'ti-check' : 'ti-copy'"></i>
          {{ copied ? '已复制' : '复制' }}
        </button>
      </template>
    </ModalDialog>
  </div>
</template>

<style scoped>
.history-page { background: var(--bg); }
.history-section { min-width: 0; }
.history-head { justify-content: space-between; }
.history-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.history-count { font-size: 12px; color: var(--t3); }
.history-filter { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.keyword-filter-input { width: min(320px, 100%); flex: 0 1 320px; }
.feedback-filter-select { width: 110px; flex: 0 0 auto; }
.date-filter-input { width: 140px; flex: 0 0 auto; }
.date-sep { color: var(--t3); font-size: 12px; }
.history-error { border-color: var(--color-danger-border); background: var(--color-danger-weak); color: var(--danger); }
.history-table th, .history-table td { white-space: nowrap; }
.history-time { color: var(--t2); }
.request-id { display: inline-block; max-width: 160px; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.principal { max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
.question { display: inline-block; max-width: 360px; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; white-space: nowrap; }
.question-sm { display: inline-block; max-width: 240px; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; white-space: nowrap; }
.template-name { display: inline-block; max-width: 160px; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; white-space: nowrap; }
.history-empty { text-align: center; color: var(--t3); padding: 28px 12px !important; }
.tdanger { background: var(--color-danger-weak); color: var(--danger); }
.count-like { color: var(--color-success); font-weight: 600; }
.count-dislike { color: var(--color-danger); font-weight: 600; }
.count-empty { color: var(--t3); }
.report-actions { display: inline-flex; align-items: center; gap: 8px; }
.report-link { border: 0; background: transparent; color: var(--primary); cursor: pointer; padding: 0; font-size: 12px; text-decoration: underline; text-underline-offset: 3px; white-space: nowrap; }
.report-link:hover { color: var(--ph); }
.feedback-tag { display: inline-flex; align-items: center; gap: 4px; height: 22px; padding: 0 7px; border-radius: var(--radius-pill); border: 1px solid var(--border); background: #fff; color: var(--t3); font-size: 11px; font-weight: 600; white-space: nowrap; }
.feedback-like { color: var(--color-success); background: var(--color-success-weak); border-color: var(--color-success-border); }
.feedback-dislike { color: var(--color-danger); background: var(--color-danger-weak); border-color: var(--color-danger-border); }
.feedback-empty { color: var(--t3); background: var(--bg-subtle); }
.prompt-loading { min-height: 260px; display: flex; align-items: center; justify-content: center; color: var(--t3); }
.prompt-viewer { width: 100%; height: 60vh; min-height: 360px; resize: none; border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 12px; outline: none; background: var(--bg-subtle); color: var(--t1); font-size: 12px; line-height: 1.7; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; white-space: pre; overflow: auto; }
.prompt-viewer:focus { border-color: var(--primary); box-shadow: var(--shadow-focus); }
.history-pagination { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding-top: 12px; color: var(--t2); font-size: 12px; flex-wrap: wrap; }
.page-size { height: 28px; border: 1px solid var(--border); border-radius: var(--radius-xs); background: #fff; color: var(--t1); padding: 0 8px; outline: none; }
.page-current { min-width: 52px; text-align: center; color: var(--t2); }
.pgb:disabled { cursor: not-allowed; opacity: .45; pointer-events: none; }
.session-content { display: flex; flex-direction: column; gap: 12px; }
.session-summary { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--bg-subtle); }
.session-meta { font-size: 12px; color: var(--t2); }
.report-table th, .report-table td { white-space: nowrap; }
.version-row > td { background: var(--bg-subtle); padding: 10px 14px !important; white-space: normal; }
.version-empty { color: var(--t3); font-size: 12px; }
.version-item { padding: 6px 0; border-bottom: 1px dashed var(--border); }
.version-item:last-child { border-bottom: 0; }
.version-line { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.version-badge { background: var(--text-1); color: #fff; padding: 1px 8px; border-radius: var(--radius-pill); font-size: 11px; font-weight: 600; }
.source-tag { display: inline-flex; align-items: center; height: 20px; padding: 0 7px; border-radius: var(--radius-pill); font-size: 11px; font-weight: 600; }
.source-generate { color: var(--color-primary-hover); background: var(--color-primary-weak); border: 1px solid var(--color-primary-border); }
.source-modify { color: var(--color-warning); background: var(--color-warning-weak); border: 1px solid var(--color-warning-border); }
.version-note { flex: 1 1 200px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--t2); }
.version-time { font-size: 12px; color: var(--t3); }
.version-feedback-meta { font-size: 11px; color: var(--t3); }
.version-comment { margin-top: 4px; padding-left: 46px; font-size: 12px; color: var(--color-danger); word-break: break-word; }
:deep(.modal.lg) { width: min(1080px, 96vw); }
:deep(.modal.lg .mb) { max-height: 74vh; overflow: auto; }
@media (max-width: 760px) {
  .question { max-width: 220px; }
  .request-id { max-width: 120px; }
}
.detail-content { display: flex; flex-direction: column; gap: 16px; }
.detail-section-title { font-size: 14px; font-weight: 600; color: var(--t1); margin: 0 0 10px; }
.detail-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.detail-item { display: flex; flex-direction: column; gap: 4px; }
.detail-item-wide { grid-column: span 2; }
.detail-label { font-size: 12px; color: var(--t3); }
.detail-value { font-size: 13px; color: var(--t1); word-break: break-word; }
</style>

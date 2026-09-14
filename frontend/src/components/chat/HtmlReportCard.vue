<script setup>
import { computed, ref } from 'vue';
import {
  buildHtmlDocument, downloadHtmlReport, downloadPngReport,
  openHtmlReportInNewTab, reportExportOverlay
} from '@/utils/htmlReport.js';

const props = defineProps({
  message: { type: Object, required: true },
  chat: { type: Object, required: true },
  // 'card' 完整卡片（默认） | 'slim' 轻量条（点击 emit locate） | 'stage' 报告页主报告区（暂同 card 渲染）
  mode: { type: String, default: 'card' }
});

defineEmits(['locate']);

const iframeRef = ref(null);
const reportDocument = computed(() => buildHtmlDocument(props.message));

function onDownloadPng() {
  downloadPngReport(props.message, iframeRef.value);
}
</script>

<template>
  <div v-if="mode === 'slim'" class="html-report-card slim">
    <div class="html-report-slim-row">
      <i class="ti ti-file-analytics" aria-hidden="true"></i>
      <span>报告已{{ (message.versionNo || 1) > 1 ? `更新至 v${message.versionNo}` : '生成' }}，已在上方报告区展示</span>
      <button type="button" class="html-download-btn secondary" @click="$emit('locate')">查看报告</button>
    </div>
  </div>

  <div v-else class="html-report-card" :class="{ stage: mode === 'stage' }">
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
          :disabled="reportExportOverlay.visible"
          @click="onDownloadPng"
        >
          <i class="ti ti-photo" aria-hidden="true"></i>下载 PNG
        </button>
        <button
          v-if="message.html"
          class="html-download-btn"
          type="button"
          :disabled="reportExportOverlay.visible"
          @click="downloadHtmlReport(message)"
        >
          <i class="ti ti-download" aria-hidden="true"></i>下载 HTML
        </button>
        <div class="report-feedback-actions" :title="chat.canSubmitReportFeedback(message) ? '评价本次报告，再次点击可取消，也可切换评价' : '暂无运行记录，无法记录反馈'">
          <button
            class="report-feedback-btn"
            :class="{ active: message.feedback === 'like' }"
            type="button"
            :disabled="!chat.canSubmitReportFeedback(message) || message.feedbackSaving"
            aria-label="点赞报告"
            @click="chat.handleReportFeedback(message, 'like')"
          >
            <i class="ti ti-thumb-up" aria-hidden="true"></i>
          </button>
          <button
            class="report-feedback-btn"
            :class="{ active: message.feedback === 'dislike', negative: true }"
            type="button"
            :disabled="!chat.canSubmitReportFeedback(message) || message.feedbackSaving"
            aria-label="点踩报告"
            @click="chat.handleReportFeedback(message, 'dislike')"
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
          @click="chat.submitDislikeFeedback(message, true)"
        >
          跳过
        </button>
        <button
          class="report-feedback-comment-btn primary"
          type="button"
          :disabled="message.feedbackSaving"
          @click="chat.submitDislikeFeedback(message, false)"
        >
          提交
        </button>
      </div>
    </div>
    <iframe
      ref="iframeRef"
      class="html-report-preview"
      :srcdoc="reportDocument"
      title="HTML报告预览"
      sandbox="allow-scripts"
    ></iframe>
  </div>
</template>

<style scoped>
/* 组件自带主题变量兜底（在 UiChatView 内会被同名变量覆盖为相同值，保证脱离聊天页也可渲染） */
.html-report-card { --P: var(--color-primary); --PL: var(--color-primary-weak); --PH: var(--color-primary-hover); --BD: var(--border-base); --BG: var(--bg-subtle); --T1: var(--text-1); --T2: var(--text-2); --T3: var(--text-3); width: min(860px, calc(100% - 46px)); border: .5px solid var(--BD); border-radius: var(--radius-lg); background: #fff; overflow: hidden; box-shadow: var(--shadow-xs); }
.html-report-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-bottom: .5px solid var(--BD); background: var(--BG); }
.html-report-head > div:first-child { min-width: 0; }
.html-report-title { font-size: 14px; font-weight: 700; color: var(--T1); }
.html-report-sub { margin-top: 2px; font-size: 11px; color: var(--T3); }
.html-report-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex: 0 0 auto; flex-wrap: nowrap; }
.report-feedback-actions { display: inline-flex; align-items: center; gap: 6px; }
.report-feedback-btn { width: 38px; height: 38px; border: .5px solid var(--BD); border-radius: var(--radius-md); background: #fff; color: var(--T3); cursor: pointer; display: inline-flex; align-items: center; justify-content: center; transition: background .15s, border-color .15s, color .15s; }
.report-feedback-btn i { font-size: 21px; }
.report-feedback-btn:hover:not(:disabled) { border-color: var(--color-primary-border); color: var(--P); background: var(--color-primary-weaker); }
.report-feedback-btn.active { color: var(--color-success); background: var(--color-success-weak); border-color: var(--color-success-border); }
.report-feedback-btn.negative.active { color: var(--color-danger); background: var(--color-danger-weak); border-color: var(--color-danger-border); }
.report-feedback-btn:disabled { cursor: not-allowed; opacity: .48; }
.html-report-feedback-error { padding: 7px 14px; border-bottom: .5px solid var(--color-danger-border); background: var(--color-danger-weak); color: var(--color-danger); font-size: 11px; }
.report-feedback-comment { padding: 10px 14px; border-bottom: .5px solid var(--BD); background: var(--bg-subtle); display: flex; flex-direction: column; gap: 8px; }
.report-feedback-comment-input { width: 100%; resize: vertical; min-height: 56px; border: .5px solid var(--BD); border-radius: var(--radius-md); padding: 8px 10px; outline: none; background: #fff; color: var(--T1); font-size: 12px; line-height: 1.6; font-family: inherit; }
.report-feedback-comment-input:focus { border-color: var(--P); box-shadow: var(--shadow-focus); }
.report-feedback-comment-actions { display: flex; justify-content: flex-end; gap: 8px; }
.report-feedback-comment-btn { height: 28px; padding: 0 12px; border: .5px solid var(--BD); border-radius: var(--radius-md); background: #fff; color: var(--T2); font-size: 12px; font-weight: 600; cursor: pointer; }
.report-feedback-comment-btn:hover:not(:disabled) { border-color: var(--P); color: var(--P); }
.report-feedback-comment-btn.primary { background: var(--P); border-color: var(--P); color: #fff; }
.report-feedback-comment-btn.primary:hover:not(:disabled) { color: #fff; filter: brightness(1.05); }
.report-feedback-comment-btn:disabled { opacity: .48; cursor: not-allowed; }
.html-download-btn { height: 32px; padding: 0 12px; border: none; border-radius: var(--radius-md); background: var(--P); color: #fff; font-size: 12px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 6px; flex-shrink: 0; }
.html-download-btn:hover { background: var(--PH); }
.html-download-btn.secondary { border: .5px solid var(--BD); background: #fff; color: var(--T2); }
.html-download-btn.secondary:hover { border-color: var(--P); background: var(--color-primary-weak); color: var(--P); }
.html-download-btn:disabled { cursor: wait; opacity: .58; }
.html-report-preview { display: block; width: 100%; min-height: 360px; max-height: 1400px; border: 0; background: #fff; }

/* stage 模式（报告页主报告区）：占满父容器宽度并加高预览，不再受 860px 上限约束 */
.html-report-card.stage { width: 100%; }
.html-report-card.stage .html-report-preview { min-height: 620px; }

/* ---- slim 轻量条（单行、与卡片同边框风格） ---- */
.html-report-slim-row { display: flex; align-items: center; gap: 10px; padding: 10px 14px; font-size: 13px; color: var(--T2); }
.html-report-slim-row > i { color: var(--P); font-size: 16px; flex-shrink: 0; }
.html-report-slim-row > span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.html-report-slim-row .html-download-btn { flex-shrink: 0; }

.html-report-version-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-strong);
}
.version-badge {
  background: var(--text-1);
  color: #fff;
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-size: 12px;
}
.version-history-toggle {
  color: var(--color-primary);
  cursor: pointer;
  font-size: 13px;
}
.html-report-history {
  padding: 8px 16px;
  background: var(--bg-subtle);
  border-bottom: 1px solid var(--border-strong);
}
.history-item {
  display: flex;
  gap: 12px;
  font-size: 13px;
  color: var(--text-2);
}
.history-action {
  color: var(--text-1);
  font-weight: 500;
}
.history-summary {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 860px) { .html-report-card { width: calc(100% - 46px); } }
</style>

<script setup>
import { computed } from 'vue';
import HtmlReportCard from './HtmlReportCard.vue';
import ThinkingStatusIcon from '../common/ThinkingStatusIcon.vue';
import TraceTemplateMatch from './TraceTemplateMatch.vue';
import { renderMarkdown } from '@/utils/markdown.js';
import { displayActivityStatus, replaceActivityStatusCodes } from '@/utils/activityDictionaries.js';
import {
  visibleTraceSteps, traceProgressText, thinkingTitleText, shouldDisplayThinkingTrace,
  stepKey, isTraceNode, isPendingStep, activityTemplateMatchResult,
  componentValueFetchSummary, componentValueCleanupText,
  activityTraceLabel, activityRouteSummary
} from '@/utils/agentTrace.js';
import {
  activityName, activityId, activityRowNumber, activityPeriod, activityTags,
  activitySummary, visibleActivities, selectionActivities,
  allActivitySelectionChecked, selectedActivityRowNumbers
} from '@/utils/activityFormat.js';

const props = defineProps({
  chat: { type: Object, required: true },
  conversation: { type: Object, required: true },
  reportCardMode: { type: String, default: 'full' }
});
const emit = defineEmits(['focus-composer', 'locate-report']);

const dynamicMessages = computed(() => props.conversation?.dynamicMessages || []);

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
  for (const item of props.conversation?.dynamicMessages || []) {
    if (item !== message && item.role === 'ai' && Array.isArray(item.selectableActivities)) {
      item.selectedIds = [];
    }
  }
  props.chat.toggleActivitySelection(message, activity);
  emit('focus-composer');
}
</script>

<template>
  <div class="divider-msg">新对话开始</div>

  <slot name="greeting"></slot>

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
            v-if="chat.isDownloadableExportMessage(message)"
            class="export-artifact-btn"
            type="button"
            @click="chat.downloadExportArtifact(message.exportArtifact)"
          >
            <i class="ti ti-download" aria-hidden="true"></i>
            下载 {{ (message.exportArtifact.format || 'HTML').toUpperCase() }} 报告
          </button>
          <div v-if="selectionActivities(message).length" class="inline-table-bulk-actions">
            <span>已选 {{ (message.selectedIds || []).length }} 行</span>
            <button
              type="button"
              :disabled="allActivitySelectionChecked(message)"
              @click="chat.setAllActivityRows(message, true)"
            >全选</button>
            <button
              type="button"
              :disabled="!(message.selectedIds || []).length"
              @click="chat.setAllActivityRows(message, false)"
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
            <div class="activity-preview-summary" style="white-space: pre-line;">{{ chat.formatApprovalDescription(message) }}</div>
          </div>
        </div>
        <div v-if="!message.resolved" class="activity-select-actions" style="margin-top: 16px; padding: 0 14px 14px;">
          <button
            class="activity-select-action"
            style="min-width: 64px;"
            type="button"
            :disabled="conversation.typing"
            @click="chat.resolveApproval(message, 'reject')"
          >
            拒绝
          </button>
          <button
            class="activity-continue-btn"
            style="min-width: 64px;"
            type="button"
            :disabled="conversation.typing"
            @click="chat.resolveApproval(message, 'approve')"
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
      <HtmlReportCard
        :message="message"
        :chat="chat"
        :mode="reportCardMode === 'slim' ? 'slim' : 'card'"
        @locate="emit('locate-report')"
      />
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
              <div v-if="componentValueFetchSummary(step)" class="trace-step-detail">
                <div class="detail-label">组件数值获取</div>
                <div class="detail-value">
                  已计算 {{ componentValueFetchSummary(step).metric_count }} 项指标<template v-if="componentValueFetchSummary(step).error_count">，{{ componentValueFetchSummary(step).error_count }} 项取数失败</template>
                </div>
              </div>
              <div v-if="componentValueCleanupText(step)" class="trace-step-detail">
                <div class="detail-label">数据清理</div>
                <div class="detail-value">{{ componentValueCleanupText(step) }}</div>
              </div>
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
  <div v-if="conversation.typing && !chat.hasRunningThinking(conversation)" class="msg-row">
    <div class="avatar av-ai"><i class="ti ti-sparkles" aria-hidden="true"></i></div>
    <div class="bubble"><div class="typing-dot"><span></span><span></span><span></span></div></div>
  </div>
</template>

<!-- 非 scoped：greeting 插槽内容由父组件渲染（携带父组件 scope id），
     这四组基础类需全局可见才能让插槽内容与组件内部同时命中。 -->
<style>
.msg-row { display: flex; gap: 12px; align-items: flex-start; }
.avatar { width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 600; }
.av-ai { background: var(--P); color: #fff; }
.bubble { max-width: 70%; background: #fff; border: .5px solid var(--BD); border-radius: var(--RAI); padding: 12px 16px; font-size: 13px; color: var(--T1); line-height: 1.55; }
.bubble p { margin: 0; }
.bubble p + p { margin-top: 8px; }
@media (max-width: 860px) { .bubble { max-width: 86%; } }
</style>

<style scoped>
.msg-row.user { flex-direction: row-reverse; }
.av-user { background: #E8F0FF; color: #0C447C; }
.bubble.user { background: var(--P); color: #fff; border-color: var(--P); border-radius: var(--RUSER); }
.bubble.user p { color: #fff; }
.typing-dot { display: inline-flex; gap: 4px; align-items: center; padding: 4px 0; }
.typing-dot span { width: 7px; height: 7px; background: var(--T3); border-radius: 50%; animation: bounce 1.2s infinite; }
.typing-dot span:nth-child(2) { animation-delay: .2s; }
.typing-dot span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-5px); } }
.divider-msg { text-align: center; font-size: 11px; color: var(--T3); display: flex; align-items: center; gap: 12px; }
.divider-msg::before, .divider-msg::after { content: ""; flex: 1; height: .5px; background: var(--BD); }

/* ---- 实时过程消息 ---- */
.system-row { align-items: center; margin-top: -10px; }
.system-msg { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 6px; background: var(--BG); font-size: 11px; color: var(--T3); line-height: 1.4; }
.system-msg i { font-size: 12px; color: var(--P); }
.export-artifact-btn { margin-top: 12px; height: 36px; padding: 0 16px; border: none; border-radius: 8px; background: var(--P); color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 7px; }
.export-artifact-btn:hover { background: var(--PH); }

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
.trace-step { display: flex; gap: 10px; padding: 8px 0; border-bottom: .5px solid #E5E6EB; }
.trace-step:last-child { border-bottom: none; }
.trace-step-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--P); margin-top: 5px; flex-shrink: 0; }
.trace-step-body { flex: 1; min-width: 0; }
.trace-step-title { font-size: 12px; font-weight: 600; color: var(--T1); }
.trace-step-message { font-size: 11px; color: var(--T3); margin-top: 2px; }
.trace-step-detail { display: flex; flex-direction: column; margin-top: 6px; padding: 6px 10px; background: #fff; border-radius: 6px; border: .5px solid var(--BD); }
.detail-label { order: 1; font-size: 10px; color: var(--T3); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 2px; }
.detail-value { order: 2; font-size: 12px; color: var(--T1); font-weight: 500; }
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

/* 与 UiChatView 输入区共用 .selected-row-circle 基础样式（两边 scoped 各持一份） */
.selected-row-circle { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; padding: 0; border: 1px solid #8fb5ff; border-radius: 50%; background: #e8f0ff; color: var(--P); font-size: 12px; font-weight: 700; line-height: 1; }
.user-selected-row-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 7px; }
.bubble.user .user-selected-row-chips .selected-row-circle { border-color: rgba(255,255,255,.72); background: rgba(255,255,255,.16); color: #fff; }

@media (max-width: 860px) { .trace-panel { max-width: 100%; } }
</style>

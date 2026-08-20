<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import TopBar from '../components/layout/TopBar.vue';
import ChatMessageList from '../components/chat/ChatMessageList.vue';
import ChatComposer from '../components/chat/ChatComposer.vue';
import HtmlReportCard from '../components/chat/HtmlReportCard.vue';
import { useAnalysisStore, REPORT_SESSION_KEY } from '../stores/analysisStore';
import { useAgentChat } from '../composables/useAgentChat';
import { useChatUrlParams } from '../composables/useChatUrlParams';
import { createConversationAPI } from '@/api/conversations.js';
import {
  downloadHtmlReport, installHtmlReportBridges, cancelPendingPngExports,
  reportExportOverlay
} from '@/utils/htmlReport.js';

const router = useRouter();
const store = useAnalysisStore();
const urlParams = useChatUrlParams();

const chatBody = ref(null);
const composerRef = ref(null);
const conversation = ref(null);
const bootError = ref('');
// 首条消息发送失败兜底：sendMessage 内部吞错写入会话，bootError 保持空
const initialSendFailed = ref(false);
// 生成时间：新建取当前时间，恢复取会话快照 createdAt
const createdAt = ref('');
// 无会话快照且前两步无有效选择 → 空态
const emptyState = ref(false);

function scrollBottom() {
  nextTick(() => {
    window.setTimeout(() => {
      if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight;
    }, 50);
  });
}

const chat = useAgentChat({
  getConversation: () => conversation.value,
  onScroll: () => scrollBottom(),
  urlParams
});

// 最新报告消息（addHtmlReport 原地更新同 requestId，新报告追加，末位即当前报告）
const latestReport = computed(() => {
  const messages = conversation.value?.dynamicMessages || [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i]?.role === 'html_report' && messages[i].html) return messages[i];
  }
  return null;
});

const generating = computed(() => Boolean(conversation.value?.typing));

// 信息头数据：优先会话快照（刷新恢复），否则取 store
const sessionContext = ref(null);
const headerInfo = computed(() => {
  const ctx = sessionContext.value;
  if (ctx) return ctx;
  const isOnline = store.state.currentType === 'online';
  return {
    type: store.state.currentType,
    typeName: isOnline ? '线上活动' : '线下活动',
    activityNames: isOnline ? [...store.state.selectedActivityNames] : [],
    period: store.lockSummary.value.period,
    compNames: store.state.canvasComps.map((c) => c.name),
    fileName: store.state.offlineFile?.file_name || ''
  };
});

const reportTitle = computed(() => latestReport.value?.title || '活动分析报告');

// 生成时间展示：YYYY-MM-DD HH:mm 本地时间，无值时不显示
const createdAtText = computed(() => {
  if (!createdAt.value) return '';
  const date = new Date(createdAt.value);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
});

function snapshotFromStore() {
  const isOnline = store.state.currentType === 'online';
  return {
    type: store.state.currentType,
    typeName: isOnline ? '线上活动' : '线下活动',
    activityNames: isOnline ? [...store.state.selectedActivityNames] : [],
    period: store.lockSummary.value.period,
    compNames: store.state.canvasComps.map((c) => c.name),
    fileName: store.state.offlineFile?.file_name || '',
    filePath: store.state.offlineFile?.file_path || '',
    offlineStart: store.state.offlineStart,
    offlineEnd: store.state.offlineEnd
  };
}

function buildInitialMessage(ctx) {
  const compPart = ctx.compNames?.length
    ? `分析框架请包含以下组件：${ctx.compNames.join('、')}。`
    : '';
  if (ctx.type === 'offline') {
    const period = ctx.offlineStart && ctx.offlineEnd ? `（统计周期 ${ctx.offlineStart} 至 ${ctx.offlineEnd}）` : '';
    return {
      text: `请基于上传的活动数据文件「${ctx.fileName}」${period}生成分析报告。${compPart}`,
      filePath: ctx.filePath || ''
    };
  }
  const names = (ctx.activityNames || []).map((n) => `「${n}」`).join('');
  return { text: `请为以下线上活动生成分析报告：${names}。${compPart}`, filePath: '' };
}

function readSession() {
  try {
    const raw = localStorage.getItem(REPORT_SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}

function writeSession(conversationId, context) {
  try {
    localStorage.setItem(REPORT_SESSION_KEY, JSON.stringify({
      conversationId,
      context,
      createdAt: new Date().toISOString()
    }));
  } catch (e) {
    console.warn('保存报告会话失败', e);
  }
}

// 刷新/恢复路径：根据快照重建会话并拉取历史
// 注意：后续调用必须传 conversation.value（响应式代理），
// 直接传原始 conv 对象时，对 dynamicMessages 的修改不会触发视图更新。
async function restoreSession(session) {
  sessionContext.value = session.context || null;
  createdAt.value = session.createdAt || '';
  const conv = chat.createConversationState({ id: session.conversationId, title: '活动分析报告' });
  conversation.value = conv;
  await chat.loadConversation(conversation.value);
  scrollBottom();
  await chat.recoverAgentRun(conversation.value);
}

// 正常路径：新建会话，组装首条消息自动开始生成
async function startNewReport() {
  const ctx = snapshotFromStore();
  sessionContext.value = ctx;
  createdAt.value = new Date().toISOString();
  const data = await createConversationAPI('新建分析对话');
  const conv = chat.createConversationState({ id: data.id, title: data.title || '新建分析对话' });
  conversation.value = conv;
  writeSession(conv.id, ctx);
  const initial = buildInitialMessage(ctx);
  await chat.sendMessage({
    text: initial.text,
    uploadedFile: initial.filePath ? { file_name: ctx.fileName, file_path: initial.filePath } : null,
    selectedRows: [],
    // 组件编排步预选的分析组件随首轮请求结构化传给后端，
    // 报告管线据此跳过活动模板匹配，直接按自选框架编排
    reportComponents: store.state.canvasComps.map((c) => ({
      name: c.name, cat: c.cat, desc: c.desc, tpl: c.tpl
    }))
  });
  // sendMessage 内部已吞错（错误写入会话消息），此处按会话状态判定首条消息是否失败
  if (!latestReport.value && !conv.typing) {
    initialSendFailed.value = true;
  }
}

async function bootstrap() {
  const session = readSession();
  bootError.value = '';
  initialSendFailed.value = false;
  emptyState.value = false;
  try {
    if (session?.conversationId) {
      await restoreSession(session);
      return;
    }
    if (!store.canGoNext.value) {
      emptyState.value = true;
      return;
    }
    await startNewReport();
  } catch (e) {
    console.error('初始化报告页失败', e);
    bootError.value = e?.message || '初始化失败';
  }
}

let uninstallBridges = null;
onMounted(() => {
  uninstallBridges = installHtmlReportBridges();
  bootstrap();
});

onBeforeUnmount(() => {
  uninstallBridges?.();
  cancelPendingPngExports();
});

function scrollToReport() {
  nextTick(() => {
    document.querySelector('.report-stage')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function scrollToRunningTrace() {
  const conv = conversation.value;
  const trace = conv?.dynamicMessages?.find((m) => m.role === 'execution_trace' && m.status === 'running');
  if (!trace || !chatBody.value) return;
  const index = conv.dynamicMessages.indexOf(trace);
  nextTick(() => {
    const target = chatBody.value.querySelector(`[data-trace-index="${index}"]`);
    if (target) chatBody.value.scrollTo({ top: target.offsetTop - 80, behavior: 'smooth' });
  });
}

function exportReport() {
  if (latestReport.value) downloadHtmlReport(latestReport.value);
}

function retryBoot() {
  store.resetReportSession();
  bootstrap();
}
</script>

<template>
  <div class="page">
    <TopBar current-label="分析报告" :step="3" />

    <!-- 空态：未经前两步直接进入 -->
    <div v-if="emptyState" class="content report-empty">
      <i class="ti ti-info-circle" style="font-size: 32px; color: var(--t3)"></i>
      <p>请先从第一步选择要分析的活动或上传线下数据</p>
      <button class="btn pri" type="button" @click="router.push({ name: 'source', params: { type: 'online' } })">
        去选择活动
      </button>
    </div>

    <template v-else>
      <div class="content report-content">
        <!-- 信息头：真实选择数据 -->
        <section class="rph">
          <div style="font-size: 14px; font-weight: 600; display: flex; gap: 8px">
            <i class="ti ti-file-analytics" style="color: var(--primary)"></i>
            <span>{{ reportTitle }}</span>
          </div>
          <div style="display: flex; gap: 16px; margin-top: 8px; font-size: 12px; flex-wrap: wrap">
            <span><span style="color: var(--t3)">活动类型：</span>{{ headerInfo.typeName }}</span>
            <span v-if="headerInfo.period"><span style="color: var(--t3)">周期：</span>{{ headerInfo.period }}</span>
            <span v-if="headerInfo.fileName"><span style="color: var(--t3)">数据文件：</span>{{ headerInfo.fileName }}</span>
            <span v-if="createdAtText"><span style="color: var(--t3)">生成时间：</span>{{ createdAtText }}</span>
          </div>
          <div v-if="headerInfo.activityNames?.length" style="margin-top: 6px; font-size: 12px">
            <span style="color: var(--t3)">所选活动：</span>{{ headerInfo.activityNames.join('、') }}
          </div>
          <div class="chips">
            <span v-for="name in headerInfo.compNames" :key="name" class="chip">{{ name }}</span>
          </div>
        </section>

        <!-- 报告区 -->
        <section class="sc report-stage">
          <div class="sh">
            <i class="ti ti-report" style="color: var(--primary)"></i>
            <span class="stitle">分析报告</span>
            <span v-if="generating" style="font-size: 12px; color: var(--t3)">正在生成…</span>
          </div>
          <HtmlReportCard v-if="latestReport" :message="latestReport" :chat="chat" mode="stage" />
          <div v-else class="report-placeholder">
            <i class="ti ti-loader-2 spinning" style="font-size: 24px; color: var(--primary)"></i>
            <p>{{ (bootError || initialSendFailed) ? `生成失败${bootError ? `：${bootError}` : ''}，可点击下方重试` : '正在根据您选择的活动与分析框架生成报告，请稍候…' }}</p>
            <button v-if="bootError || initialSendFailed" class="btn" type="button" @click="retryBoot">
              <i class="ti ti-refresh"></i> 重试
            </button>
          </div>
        </section>

        <!-- AI 问答区 -->
        <section class="sc report-chat">
          <div class="sh">
            <i class="ti ti-message-question" style="color: var(--primary)"></i>
            <span class="stitle">AI报告问答</span>
          </div>
          <div ref="chatBody" class="report-chat-body">
            <ChatMessageList
              v-if="conversation"
              :chat="chat"
              :conversation="conversation"
              report-card-mode="slim"
              @focus-composer="composerRef?.focus()"
              @locate-report="scrollToReport"
            />
          </div>
          <ChatComposer
            v-if="conversation"
            ref="composerRef"
            :chat="chat"
            :conversation="conversation"
            @locate-trace="scrollToRunningTrace"
          />
        </section>
      </div>

      <div class="fbar">
        <button class="btn" type="button" @click="router.push({ name: 'compose' })">
          <i class="ti ti-arrow-left"></i> 返回调整
        </button>
        <button class="btn pri" type="button" :disabled="!latestReport" @click="exportReport">
          <i class="ti ti-download"></i> 导出HTML
        </button>
      </div>
    </template>

    <div v-if="reportExportOverlay.visible" class="report-export-overlay" role="status">
      <div class="report-export-loading">
        <i class="ti ti-loader-2 report-export-spinner"></i>
        <span>{{ reportExportOverlay.label }}</span>
        <small>请稍候，不要关闭当前页面</small>
      </div>
    </div>
  </div>
</template>

<style scoped>
.report-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--t3); }
/* 聊天组件（ChatMessageList/ChatComposer）的设计变量定义在 UiChatView 的 .ui-chat-page 上，
   这里按同值补齐，否则 var(--BD)/var(--P) 等未定义会导致气泡边框、背景整条失效 */
.report-chat { --P: #165DFF; --PL: #E8F0FF; --PH: #0E47CC; --BD: #E5E6EB; --BG: #F7F8FA; --T1: #1D2129; --T2: #4E5969; --T3: #86909C; --RAI: 16px 16px 4px 16px; --RUSER: 16px 4px 16px 16px; }
/* 消息区用浅灰底（同 /chat-ui 页面底色），白色气泡与 slim 报告卡片才有可见边界 */
.report-chat-body { max-height: 420px; overflow-y: auto; padding: 12px; background: var(--BG); border-radius: 8px; }
.report-placeholder { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 48px 0; color: var(--t3); font-size: 13px; }
.spinning { animation: report-spin 1s linear infinite; }
@keyframes report-spin { to { transform: rotate(360deg); } }
/* 导出遮罩（UiChatView 中为组件 scoped 样式，这里按报告页变量补齐） */
.report-export-overlay { position: fixed; inset: 0; z-index: 9999; display: flex; align-items: center; justify-content: center; padding: 24px; background: rgba(15, 23, 42, .34); backdrop-filter: blur(2px); }
.report-export-loading { min-width: 240px; display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 24px 28px; border: .5px solid rgba(255, 255, 255, .7); border-radius: 14px; background: rgba(255, 255, 255, .96); color: var(--t1); font-size: 14px; font-weight: 700; box-shadow: 0 18px 48px rgba(15, 23, 42, .2); }
.report-export-loading small { color: var(--t3); font-size: 11px; font-weight: 400; }
.report-export-spinner { color: var(--primary); font-size: 34px; animation: report-spin .9s linear infinite; }
</style>

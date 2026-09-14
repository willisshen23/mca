<script setup>
// 独立版组件编排页（/main/analysis/compose）：内容复制自 SkillComposerView，
// 通过路由 meta.standalone 脱离管理后台框架（无侧边栏）单独访问。
// 上一步回到 /main，生成报告跳转 /main/analysis/report，URL 挂参全程透传。
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import TopBar from '../components/layout/TopBar.vue';
import MainHero from '../components/layout/MainHero.vue';
import SkillLibrary from '../components/skills/SkillLibrary.vue';
import SkillCanvas from '../components/skills/SkillCanvas.vue';
import { useAnalysisStore } from '../stores/analysisStore';
import { applyActivityTemplate, fetchActivityTemplates } from '../api/skills';

const router = useRouter();
const route = useRoute();
const store = useAnalysisStore();
const lockSummary = store.lockSummary;

const templates = ref([]);
const templatesLoading = ref(false);
const allSkills = ref([]);

// 数据源活动清单浮层：线上活动已选清单，点击「N项线上活动」展开
const activityListOpen = ref(false);
const sourceRef = ref(null);
const isOnline = computed(() => store.state.currentType === 'online');
const selectedActivities = computed(() => [...store.state.selectedActivityNames]);
// 画布为空（未选任何分析组件）时禁止生成报告
const hasCanvasSkills = computed(() => store.state.canvasComps.length > 0);

function handleDocumentClick(event) {
  if (sourceRef.value && !sourceRef.value.contains(event.target)) {
    activityListOpen.value = false;
  }
}

async function loadTemplates() {
  templatesLoading.value = true;
  try {
    templates.value = await fetchActivityTemplates();
  } catch {
    templates.value = [];
  } finally {
    templatesLoading.value = false;
  }
}

function handleSkillsLoaded(skills) {
  allSkills.value = skills;
  store.setCanvasDefaults(skills);
}

function resolveSkill(name) {
  return allSkills.value.find((item) => item.name === name) || { name, cat: '通用分析', desc: '' };
}

async function applyTemplate(tpl) {
  if (store.state.activeTemplateName === tpl.name) return;
  store.applyTemplateToCanvas(tpl.skills.map(resolveSkill), tpl.name);
  try {
    await applyActivityTemplate(tpl.id);
  } catch {
    // 应用次数统计失败不影响模板使用
  }
}

function goBack() {
  router.push({ name: 'main-source', query: { ...route.query } });
}

function goReport() {
  store.resetReportSession();
  router.push({ name: 'main-report', query: { ...route.query } });
}

// 跳转历史对话页（/chat-ui），透传当前页面所有 URL 参数（srcSysNo、userId、orgNo 等）
function goHistory() {
  router.push({ name: 'chat-ui', query: { ...route.query } });
}

onMounted(() => {
  loadTemplates();
  document.addEventListener('click', handleDocumentClick);
});

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick);
});
</script>

<template>
  <div class="page">
    <MainHero />
    <TopBar current-label="组件编排" :step="2">
      <button class="btn sm ghost history-btn" type="button" @click="goHistory">
        <i class="ti ti-history"></i> 查看历史对话
      </button>
    </TopBar>
    <div style="padding: 10px 20px; flex-shrink: 0">
      <div class="lkbar">
        <i class="ti ti-lock"></i>
        <div class="lkv"><span class="lkk">活动类型：</span><span class="lkvv">{{ lockSummary.typeName }}</span></div>
        <div class="lkv source-anchor" ref="sourceRef">
          <span class="lkk">数据源：</span>
          <button
            v-if="isOnline && selectedActivities.length"
            type="button"
            class="lkvv source-trigger"
            :class="{ open: activityListOpen }"
            @click.stop="activityListOpen = !activityListOpen"
          >
            {{ lockSummary.source }}
            <i class="ti ti-chevron-down source-trigger-arrow"></i>
          </button>
          <span v-else class="lkvv">{{ lockSummary.source }}</span>
          <transition name="source-pop-fade">
            <div v-if="activityListOpen" class="source-pop">
              <div class="source-pop-head">
                <i class="ti ti-list-check"></i> 已选活动（{{ selectedActivities.length }}）
              </div>
              <ul class="source-pop-list">
                <li v-for="(name, index) in selectedActivities" :key="name">
                  <span class="source-pop-idx">{{ index + 1 }}</span>
                  <span class="source-pop-name">{{ name }}</span>
                </li>
              </ul>
            </div>
          </transition>
        </div>
      </div>
    </div>
    <div class="content composer-content" style="overflow: hidden; padding: 0 20px 10px; flex: 1; display: flex; flex-direction: column; min-height: 0">
      <div class="three composer-grid">
        <SkillLibrary @add="store.addCanvasSkill" @loaded="handleSkillsLoaded" />
        <div class="canvas-col">
          <div class="tpl-strip">
            <div class="tpl-strip-head">
              <span class="tpl-strip-title"><i class="ti ti-layout-cards"></i> 选择分析模板</span>
              <span class="tpl-strip-hint">点击模板，一键替换下方分析组件，仍可拖拽微调</span>
            </div>
            <div class="tpl-strip-list">
              <button
                v-for="tpl in templates"
                :key="tpl.id"
                type="button"
                class="tpl-chip"
                :class="{ active: store.state.activeTemplateName === tpl.name }"
                :title="tpl.desc"
                @click="applyTemplate(tpl)"
              >
                <span class="tpl-chip-icon" :style="{ background: tpl.bg }">
                  <i :class="['ti', tpl.icon]" :style="{ color: tpl.color }"></i>
                </span>
                <span class="tpl-chip-text">
                  <span class="tpl-chip-name">{{ tpl.name }}</span>
                  <span class="tpl-chip-cnt">{{ tpl.skills.length }} 个组件</span>
                </span>
                <i v-if="store.state.activeTemplateName === tpl.name" class="ti ti-check tpl-chip-check"></i>
              </button>
              <span v-if="templatesLoading" class="tpl-strip-loading">正在加载模板...</span>
              <span v-else-if="templates.length === 0" class="tpl-strip-loading">暂无可用模板</span>
            </div>
          </div>
          <SkillCanvas />
        </div>
      </div>
    </div>
    <div class="fbar">
      <button class="btn" type="button" @click="goBack">
        <i class="ti ti-arrow-left"></i> 上一步
      </button>
      <button
        class="btn pri"
        type="button"
        :disabled="!hasCanvasSkills"
        title="请先从左侧组件库添加分析组件"
        @click="goReport"
      >
        生成分析报告 <i class="ti ti-report"></i>
      </button>
    </div>
  </div>
</template>

<style scoped>
.history-btn {
  margin-left: 8px;
  white-space: nowrap;
}

/* 数据源活动清单：可点触发器 + 浮层 */
.source-anchor {
  position: relative;
}

.source-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  padding: 2px 6px;
  margin: -2px -6px;
  font-size: 12px;
  color: var(--primary);
  cursor: pointer;
  transition: background .15s, border-color .15s;
}

.source-trigger:hover,
.source-trigger.open {
  background: var(--pl, var(--color-primary-weak));
  border-color: var(--color-primary-border);
}

.source-trigger-arrow {
  font-size: 12px;
  transition: transform .15s;
}

.source-trigger.open .source-trigger-arrow {
  transform: rotate(180deg);
}

.source-pop {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 60;
  min-width: 280px;
  max-width: 420px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  padding: 10px 12px 12px;
}

.source-pop-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--t1);
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.source-pop-head i {
  color: var(--primary);
}

.source-pop-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.source-pop-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--t1);
}

.source-pop-idx {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--pl, var(--color-primary-weak));
  color: var(--primary);
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.source-pop-name {
  word-break: break-all;
}

.source-pop-fade-enter-active,
.source-pop-fade-leave-active {
  transition: opacity .15s, transform .15s;
}

.source-pop-fade-enter-from,
.source-pop-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* 去掉右侧指令面板后改为两栏布局 */
.composer-grid {
  grid-template-columns: 250px minmax(0, 1fr);
}

.canvas-col {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
}

.canvas-col .canvas {
  flex: 1;
  min-height: 0;
}

/* 模板选择条 */
.tpl-strip {
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: var(--r);
  background: #fff;
  padding: 10px 12px 12px;
}

.tpl-strip-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 9px;
}

.tpl-strip-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--t1);
}

.tpl-strip-title i {
  color: var(--primary);
  margin-right: 3px;
}

.tpl-strip-hint {
  font-size: 11px;
  color: var(--t3);
}

.tpl-strip-list {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 2px;
}

.tpl-chip {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px 7px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-subtle);
  cursor: pointer;
  text-align: left;
  transition: border-color .15s, background .15s, box-shadow .15s;
}

.tpl-chip:hover {
  border-color: var(--color-primary-border);
  background: #fff;
}

.tpl-chip.active {
  border-color: var(--primary);
  background: var(--pl);
  box-shadow: var(--shadow-md);
}

.tpl-chip-icon {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  flex-shrink: 0;
}

.tpl-chip-text {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.tpl-chip-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--t1);
  white-space: nowrap;
}

.tpl-chip.active .tpl-chip-name {
  color: var(--primary);
}

.tpl-chip-cnt {
  font-size: 11px;
  color: var(--t3);
  white-space: nowrap;
}

.tpl-chip-check {
  color: var(--primary);
  font-size: 14px;
  margin-left: 2px;
}

.tpl-strip-loading {
  align-self: center;
  font-size: 12px;
  color: var(--t3);
  padding: 0 6px;
}
</style>

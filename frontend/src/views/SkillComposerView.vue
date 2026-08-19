<script setup>
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import TopBar from '../components/layout/TopBar.vue';
import SkillLibrary from '../components/skills/SkillLibrary.vue';
import SkillCanvas from '../components/skills/SkillCanvas.vue';
import { useAnalysisStore } from '../stores/analysisStore';
import { applyActivityTemplate, fetchActivityTemplates } from '../api/skills';

const router = useRouter();
const store = useAnalysisStore();
const lockSummary = store.lockSummary;

const templates = ref([]);
const templatesLoading = ref(false);
const allSkills = ref([]);

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

function goReport() {
  store.resetReportSession();
  router.push({ name: 'report' });
}

onMounted(loadTemplates);
</script>

<template>
  <div class="page">
    <TopBar current-label="组件编排" :step="2" />
    <div style="padding: 10px 20px; flex-shrink: 0">
      <div class="lkbar">
        <i class="ti ti-lock"></i>
        <div class="lkv"><span class="lkk">活动类型：</span><span class="lkvv">{{ lockSummary.typeName }}</span></div>
        <div class="lkv"><span class="lkk">数据源：</span><span class="lkvv">{{ lockSummary.source }}</span></div>
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
                type="button"
                class="tpl-chip"
                :class="{ active: !store.state.activeTemplateName }"
                @click="store.resetCanvas"
              >
                <span class="tpl-chip-icon default"><i class="ti ti-sparkles"></i></span>
                <span class="tpl-chip-text">
                  <span class="tpl-chip-name">AI 默认框架</span>
                  <span class="tpl-chip-cnt">{{ store.state.defaultCanvasComps.length }} 个组件</span>
                </span>
                <i v-if="!store.state.activeTemplateName" class="ti ti-check tpl-chip-check"></i>
              </button>
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
      <button class="btn ghost" type="button" @click="store.resetCanvas">
        <i class="ti ti-refresh"></i> 重置AI默认框架
      </button>
      <button class="btn" type="button" @click="router.push({ name: 'source', params: { type: store.state.currentType } })">
        <i class="ti ti-arrow-left"></i> 上一步
      </button>
      <button class="btn pri" type="button" @click="goReport">
        生成分析报告 <i class="ti ti-report"></i>
      </button>
    </div>
  </div>
</template>

<style scoped>
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
  border-radius: 8px;
  background: #fbfcfe;
  cursor: pointer;
  text-align: left;
  transition: border-color .15s, background .15s, box-shadow .15s;
}

.tpl-chip:hover {
  border-color: #a9c4ff;
  background: #fff;
}

.tpl-chip.active {
  border-color: var(--primary);
  background: var(--pl);
  box-shadow: 0 2px 8px rgba(22, 93, 255, .1);
}

.tpl-chip-icon {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  flex-shrink: 0;
}

.tpl-chip-icon.default {
  background: #edf3ff;
  color: var(--primary);
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
  font-size: 10px;
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

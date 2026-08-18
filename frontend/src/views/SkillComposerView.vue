<script setup>
import { useRouter } from 'vue-router';
import TopBar from '../components/layout/TopBar.vue';
import ChatPanel from '../components/common/ChatPanel.vue';
import SkillLibrary from '../components/skills/SkillLibrary.vue';
import SkillCanvas from '../components/skills/SkillCanvas.vue';
import { useAnalysisStore } from '../stores/analysisStore';

const router = useRouter();
const store = useAnalysisStore();
const lockSummary = store.lockSummary;

function sendMessage(value) {
  store.addS2Message('usr', value);
  window.setTimeout(() => {
    store.addS2Message('ai', '指令已接收，您也可以拖拽或双击左侧卡片。');
  }, 200);
}
</script>

<template>
  <div class="page">
    <TopBar current-label="组件编排" :step="2" />
    <div style="padding: 10px 20px; flex-shrink: 0">
      <div class="lkbar">
        <i class="ti ti-lock"></i>
        <div class="lkv"><span class="lkk">活动类型：</span><span class="lkvv">{{ lockSummary.typeName }}</span></div>
        <div class="lkv"><span class="lkk">数据源：</span><span class="lkvv">{{ lockSummary.source }}</span></div>
        <div class="lkv"><span class="lkk">统计周期：</span><span class="lkvv">{{ lockSummary.period }}</span></div>
      </div>
    </div>
    <div class="content composer-content" style="overflow: hidden; padding: 0 20px 10px; flex: 1; display: flex; flex-direction: column; min-height: 0">
      <div class="three">
        <SkillLibrary @add="store.addCanvasSkill" @loaded="store.setCanvasDefaults" />
        <SkillCanvas />
        <ChatPanel :messages="store.state.s2Messages" title="活动分析助手" @send="sendMessage" />
      </div>
    </div>
    <div class="fbar">
      <button class="btn ghost" type="button" @click="store.resetCanvas">
        <i class="ti ti-refresh"></i> 重置AI默认框架
      </button>
      <button class="btn" type="button" @click="router.push({ name: 'source', params: { type: store.state.currentType } })">
        <i class="ti ti-arrow-left"></i> 上一步
      </button>
      <button class="btn pri" type="button" @click="router.push({ name: 'report' })">
        生成分析报告 <i class="ti ti-report"></i>
      </button>
    </div>
  </div>
</template>

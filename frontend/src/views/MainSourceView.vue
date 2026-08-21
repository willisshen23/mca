<script setup>
// 独立版数据源配置页（/main）：内容复制自 SourceConfigView 的线上活动页，
// 通过路由 meta.standalone 脱离管理后台框架（无侧边栏）单独访问。
import { computed, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import TopBar from '../components/layout/TopBar.vue';
import MainHero from '../components/layout/MainHero.vue';
import OnlineSourceConfig from '../components/source/OnlineSourceConfig.vue';
import { useAnalysisStore, MAX_SELECTED_ACTIVITIES } from '../stores/analysisStore';

const router = useRouter();
const route = useRoute();
const store = useAnalysisStore();
const canGoNext = store.canGoNext;
const selectedCount = store.selectedCount;

const badge = computed(() => `当前分析类型：${store.state.currentType === 'online' ? '线上活动' : '线下活动'}`);
const badgeMode = computed(() => (store.state.currentType === 'online' ? 'ton' : 'toff'));

onMounted(() => {
  store.setAnalysisType('online');
});

function goCompose() {
  if (!canGoNext.value) return;
  router.push({ name: 'main-compose', query: { ...route.query } });
}

// 跳转历史对话页（/chat-ui），透传当前页面所有 URL 参数（srcSysNo、userId、orgNo 等）
function goHistory() {
  router.push({ name: 'chat-ui', query: { ...route.query } });
}
</script>

<template>
  <div class="page">
    <MainHero />
    <TopBar current-label="活动分析" :step="1" :badge="badge" :badge-mode="badgeMode">
      <button class="btn sm ghost history-btn" type="button" @click="goHistory">
        <i class="ti ti-history"></i> 查看历史对话
      </button>
    </TopBar>
    <div class="content">
      <OnlineSourceConfig :show-selected-bar="false" />
    </div>
    <div class="fbar">
      <div v-if="selectedCount > 0" class="selbar fbar-selbar">
        <i class="ti ti-check-circle"></i>
        <span>已选 {{ selectedCount }}/{{ MAX_SELECTED_ACTIVITIES }} 个活动</span>
        <span style="margin-left: auto; font-size: 11px">统计时间自动取所选活动时间合集</span>
      </div>
      <button class="btn dis" type="button">上一步</button>
      <button class="btn pri" :class="{ dis: !canGoNext }" type="button" @click="goCompose">
        下一步 <i class="ti ti-arrow-right"></i>
      </button>
    </div>
  </div>
</template>

<style scoped>
.history-btn {
  margin-left: 8px;
  white-space: nowrap;
}

/* 已选活动回显条放在底部按钮栏左侧，常驻可见无需滚动 */
.fbar-selbar {
  margin-top: 0;
  margin-right: auto;
  flex: 1;
  min-width: 260px;
}
</style>

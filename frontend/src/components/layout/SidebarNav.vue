<script setup>
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAnalysisStore } from '../../stores/analysisStore';

const route = useRoute();
const router = useRouter();
const store = useAnalysisStore();

const activeKey = computed(() => {
  if (route.name === 'main') return 'main';
  if (['source', 'compose', 'report'].includes(route.name)) return store.state.currentType;
  if (route.name === 'skills') return 'skills';
  if (route.name === 'history') return 'history';
  if (route.name === 'conversation-logs') return 'conversation-logs';
  if (route.name === 'templates') return 'templates';
  if (route.name === 'logs') return 'logs';
  if (route.name === 'chat-ui') return 'chat-ui';
  if (route.name === 'settings') return 'settings';
  return '';
});

function startAnalysis(type) {
  store.setAnalysisType(type, true);
  router.push({ name: 'source', params: { type } });
}
</script>

<template>
  <aside class="sb" aria-label="主导航">
    <RouterLink class="logo" to="/main" aria-label="管理首页">
      <i class="ti ti-chart-dots-3"></i>
    </RouterLink>
    <RouterLink class="ni" :class="{ active: activeKey === 'main' }" to="/main">
      <i class="ti ti-home"></i>
      <span>首页</span>
    </RouterLink>
    <button class="ni" :class="{ active: activeKey === 'online' }" type="button" @click="startAnalysis('online')">
      <i class="ti ti-device-desktop-analytics"></i>
      <span>线上</span>
    </button>
    <button class="ni" :class="{ active: activeKey === 'offline' }" type="button" @click="startAnalysis('offline')">
      <i class="ti ti-building-store"></i>
      <span>线下</span>
    </button>
    <RouterLink class="ni" :class="{ active: activeKey === 'skills' }" to="/skills">
      <i class="ti ti-brain"></i>
      <span>SKILL</span>
    </RouterLink>
    <RouterLink class="ni" :class="{ active: activeKey === 'templates' }" to="/templates">
      <i class="ti ti-layout-cards"></i>
      <span>模板</span>
    </RouterLink>
    <RouterLink class="ni" :class="{ active: activeKey === 'chat-ui' }" to="/chat-ui">
      <i class="ti ti-message-circle"></i>
      <span>对话</span>
    </RouterLink>
    <RouterLink class="ni nb" :class="{ active: activeKey === 'history' }" to="/history">
      <i class="ti ti-history"></i>
      <span>历史</span>
    </RouterLink>
    <RouterLink class="ni" :class="{ active: activeKey === 'conversation-logs' }" to="/conversation-logs">
      <i class="ti ti-messages"></i>
      <span>记录</span>
    </RouterLink>
    <RouterLink class="ni" :class="{ active: activeKey === 'logs' }" to="/logs">
      <i class="ti ti-file-text"></i>
      <span>日志</span>
    </RouterLink>
    <RouterLink class="ni" :class="{ active: activeKey === 'settings' }" to="/settings">
      <i class="ti ti-settings"></i>
      <span>设置</span>
    </RouterLink>
  </aside>
</template>

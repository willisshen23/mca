<script setup>
import { computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import TopBar from '../components/layout/TopBar.vue';
import OnlineSourceConfig from '../components/source/OnlineSourceConfig.vue';
import OfflineSourceConfig from '../components/source/OfflineSourceConfig.vue';
import { useAnalysisStore } from '../stores/analysisStore';

const route = useRoute();
const router = useRouter();
const store = useAnalysisStore();
const canGoNext = store.canGoNext;

const badge = computed(() => `当前分析类型：${store.state.currentType === 'online' ? '线上活动' : '线下活动'}`);
const badgeMode = computed(() => (store.state.currentType === 'online' ? 'ton' : 'toff'));

watch(
  () => route.params.type,
  (type) => {
    store.setAnalysisType(type);
  },
  { immediate: true }
);

function goCompose() {
  if (!canGoNext.value) return;
  router.push({ name: 'compose' });
}
</script>

<template>
  <div class="page">
    <TopBar current-label="活动分析" :step="1" :badge="badge" :badge-mode="badgeMode" />
    <div class="content">
      <OnlineSourceConfig v-if="store.state.currentType === 'online'" />
      <OfflineSourceConfig v-else />
    </div>
    <div class="fbar">
      <button class="btn dis" type="button">上一步</button>
      <button class="btn pri" :class="{ dis: !canGoNext }" type="button" @click="goCompose">
        下一步 <i class="ti ti-arrow-right"></i>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import SidebarNav from './components/layout/SidebarNav.vue';
import FloatingAssistant from './components/common/FloatingAssistant.vue';

const route = useRoute();
const isStandalone = computed(() => Boolean(route.meta.standalone));
</script>

<template>
  <RouterView v-if="isStandalone" />
  <div v-else class="app">
    <SidebarNav />
    <main class="main">
      <RouterView />
      <FloatingAssistant />
    </main>
  </div>
</template>

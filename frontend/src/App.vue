<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import SidebarNav from './components/layout/SidebarNav.vue';

const route = useRoute();
const isStandalone = computed(() => Boolean(route.meta.standalone));
</script>

<template>
  <RouterView v-if="isStandalone" />
  <div v-else class="app">
    <SidebarNav />
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>

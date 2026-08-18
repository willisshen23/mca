<script setup>
import StepIndicator from './StepIndicator.vue';

defineProps({
  currentLabel: {
    type: String,
    default: ''
  },
  step: {
    type: Number,
    default: 0
  },
  title: {
    type: String,
    default: '活动分析助手'
  },
  badge: {
    type: String,
    default: ''
  },
  badgeMode: {
    type: String,
    default: 'ton'
  }
});
</script>

<template>
  <div class="topbar">
    <div class="bc">
      <span>{{ title }}</span>
      <i v-if="currentLabel" class="ti ti-chevron-right"></i>
      <span v-if="currentLabel" class="cur">{{ currentLabel }}</span>
    </div>
    <span v-if="badge" class="tbadge" :class="badgeMode">{{ badge }}</span>
    <StepIndicator v-if="step" :current="step" />
    <slot />
  </div>
</template>

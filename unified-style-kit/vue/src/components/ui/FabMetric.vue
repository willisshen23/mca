<!-- FAB 统一风格 —— KPI 指标卡 -->
<template>
  <div :class="['fab-metric', { 'fab-metric--accent': accent }]">
    <div class="fab-metric__label"><slot name="icon" />{{ label }}</div>
    <div class="fab-metric__value">
      {{ value }}<span v-if="unit" class="unit">{{ unit }}</span>
    </div>
    <div v-if="trend" :class="['fab-metric__trend', `fab-metric__trend--${trendDir}`]">{{ trend }}</div>
  </div>
</template>

<script setup>
defineProps({
  label:    { type: String, required: true },
  value:    { type: [String, Number], required: true },
  unit:     { type: String, default: '' },
  trend:    { type: String, default: '' },
  trendDir: { type: String, default: 'flat' },  // up | down | flat
  accent:   { type: Boolean, default: false },
})
</script>

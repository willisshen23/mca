<!-- FAB 统一风格 —— 卡片 -->
<template>
  <div :class="['fab-card', { 'fab-card--hoverable': hoverable, 'fab-card--flat': flat }]">
    <div v-if="title || $slots.extra" class="fab-card__header">
      <div>
        <div v-if="title" class="fab-card__title">{{ title }}</div>
        <div v-if="subtitle" class="fab-card__subtitle">{{ subtitle }}</div>
      </div>
      <div v-if="$slots.extra" class="fab-card__extra"><slot name="extra" /></div>
    </div>
    <div class="fab-card__body"><slot /></div>
    <div v-if="$slots.footer" class="fab-card__footer"><slot name="footer" /></div>
  </div>
</template>

<script setup>
defineProps({
  title:     { type: String,  default: '' },
  subtitle:  { type: String,  default: '' },
  hoverable: { type: Boolean, default: false },
  flat:      { type: Boolean, default: false },
})
</script>

<!-- FAB 统一风格 —— 标签 -->
<template>
  <span :class="['fab-tag', tone !== 'default' && `fab-tag--${tone}`, { 'fab-tag--pill': pill }]">
    <slot />
  </span>
</template>

<script setup>
defineProps({
  // default | primary | success | warning | danger | violet
  tone: { type: String,  default: 'default' },
  pill: { type: Boolean, default: false },
})
</script>

<!-- FAB 统一风格 —— 按钮（新页面用；老页面沿用 .btn + fab-theme.css 即可） -->
<template>
  <button
    :class="[
      'fab-btn',
      variant !== 'default' && `fab-btn--${variant}`,
      size !== 'md' && `fab-btn--${size}`,
      { 'fab-btn--pill': pill, 'fab-btn--block': block, 'fab-btn--icon': icon },
    ]"
    :disabled="disabled"
  >
    <slot name="icon" />
    <slot />
  </button>
</template>

<script setup>
defineProps({
  // primary | outline | text | danger | danger-ghost | default
  variant:  { type: String,  default: 'default' },
  size:     { type: String,  default: 'md' },   // sm | md | lg
  pill:     { type: Boolean, default: false },
  block:    { type: Boolean, default: false },
  icon:     { type: Boolean, default: false },  // 纯图标按钮
  disabled: { type: Boolean, default: false },
})
</script>

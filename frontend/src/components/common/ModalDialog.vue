<script setup>
defineProps({
  open: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    required: true
  },
  large: {
    type: Boolean,
    default: false
  },
  danger: {
    type: Boolean,
    default: false
  },
  closeOnBackdrop: {
    type: Boolean,
    default: true
  }
});

defineEmits(['close']);
</script>

<template>
  <div class="mbk" :class="{ show: open }" @click.self="closeOnBackdrop && $emit('close')">
    <div class="modal" :class="{ lg: large }" role="dialog" aria-modal="true" :aria-label="title">
      <div class="mh">
        <h3 :class="{ danger: danger }">
          <i v-if="danger" class="ti ti-alert-triangle" style="font-size: 15px; vertical-align: -2px; margin-right: 4px"></i>
          {{ title }}
        </h3>
        <button class="mc" type="button" aria-label="关闭" @click="$emit('close')">
          <i class="ti ti-x"></i>
        </button>
      </div>
      <div class="mb">
        <slot />
      </div>
      <div class="mf">
        <slot name="footer">
          <button class="btn" type="button" @click="$emit('close')">取消</button>
          <button class="btn pri" type="button" @click="$emit('close')">保存</button>
        </slot>
      </div>
    </div>
  </div>
</template>

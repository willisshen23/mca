<script setup>
defineProps({
  items: {
    type: Array,
    required: true
  }
});
</script>

<template>
  <div class="barchart">
    <div v-for="item in items" :key="item.label" class="brow">
      <span class="blabel">{{ item.label }}</span>
      <div class="btrack">
        <div class="bfill" :style="{ width: `${item.value}%` }"></div>
      </div>
      <span class="bval">{{ item.value }}%</span>
    </div>
  </div>
</template>

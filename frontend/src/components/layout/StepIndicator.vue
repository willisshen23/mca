<script setup>
defineProps({
  current: {
    type: Number,
    required: true
  }
});

const steps = ['数据源配置', '组件编排', '分析报告'];
</script>

<template>
  <div class="steps" aria-label="分析步骤">
    <template v-for="(step, index) in steps" :key="step">
      <div class="st" :class="{ active: current === index + 1, done: current > index + 1 }">
        <div class="sd">
          <i v-if="current > index + 1" class="ti ti-check"></i>
          <span v-else>{{ index + 1 }}</span>
        </div>
        <span>{{ step }}</span>
      </div>
      <div v-if="index < steps.length - 1" class="sl" :class="{ done: current > index + 1 }"></div>
    </template>
  </div>
</template>

<script setup>
defineProps({
  status: {
    type: String,
    default: 'done'
  }
});
</script>

<template>
  <svg
    class="thinking-status-icon"
    :class="`is-${status}`"
    :viewBox="status === 'running' ? '0 0 32 32' : '0 0 36 36'"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <template v-if="status === 'running'">
      <circle class="thinking-status-icon__track" cx="16" cy="16" r="10" />
      <g class="thinking-status-icon__orbit">
        <circle class="thinking-status-icon__progress" cx="16" cy="16" r="10" />
        <circle class="thinking-status-icon__progress-dot" cx="16" cy="6" r="1.8" />
      </g>
      <path class="thinking-status-icon__center-spark" d="M16 11.4c.4 2.75 1.85 4.2 4.6 4.6-2.75.4-4.2 1.85-4.6 4.6-.4-2.75-1.85-4.2-4.6-4.6 2.75-.4 4.2-1.85 4.6-4.6Z" />
    </template>

    <template v-else-if="status === 'paused'">
      <path d="M23.1 12.2A11 11 0 1 0 25.4 24" />
      <path class="thinking-status-icon__pause" d="M11.5 16v9M17.5 16v9" />
      <path class="thinking-status-icon__spark" d="M21 6.5c.3 2.1 1.4 3.2 3.5 3.5-2.1.3-3.2 1.4-3.5 3.5-.3-2.1-1.4-3.2-3.5-3.5 2.1-.3 3.2-1.4 3.5-3.5Z" />
    </template>

    <template v-else>
      <image
        class="thinking-status-icon__asset"
        href="/analysis-complete-icon.png"
        x="-5"
        y="-2"
        width="46"
        height="40"
        preserveAspectRatio="none"
      />
    </template>
  </svg>
</template>

<style scoped>
.thinking-status-icon {
  display: block;
  width: 28px;
  height: 28px;
  overflow: visible;
  color: #165dff;
  stroke: currentColor;
  stroke-width: 2.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.thinking-status-icon__orbit {
  transform-box: view-box;
  transform-origin: 16px 16px;
  animation: thinking-orbit 1.15s linear infinite;
}

.thinking-status-icon__track,
.thinking-status-icon__progress {
  fill: none;
}

.thinking-status-icon__track {
  stroke: #dbe7ff;
  stroke-width: 2.4;
}

.thinking-status-icon__progress {
  stroke: currentColor;
  stroke-width: 3;
  stroke-dasharray: 43 20;
  transform-box: view-box;
  transform: rotate(-90deg);
  transform-origin: 16px 16px;
}

.thinking-status-icon__progress-dot,
.thinking-status-icon__center-spark,
.thinking-status-icon__spark {
  stroke: none;
}

.thinking-status-icon__progress-dot { fill: #6f56ff; }
.thinking-status-icon__center-spark { fill: currentColor; }
.thinking-status-icon__spark { fill: currentColor; }

.thinking-status-icon__pause {
  stroke-width: 3.4;
}

.thinking-status-icon__asset {
  image-rendering: auto;
}

.thinking-status-icon.is-paused {
  color: #86909c;
}

@keyframes thinking-orbit {
  to { transform: rotate(360deg); }
}
</style>

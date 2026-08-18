<script setup>
import { nextTick, ref, watch } from 'vue';

const props = defineProps({
  title: {
    type: String,
    default: '活动分析助手'
  },
  messages: {
    type: Array,
    required: true
  },
  placeholder: {
    type: String,
    default: '输入指令...'
  }
});

const emit = defineEmits(['send']);
const input = ref('');
const chatRef = ref(null);

function send() {
  const value = input.value.trim();
  if (!value) return;
  emit('send', value);
  input.value = '';
}

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight;
  },
  { immediate: true }
);
</script>

<template>
  <div class="aip">
    <div class="aiph">
      <i class="ti ti-message-circle" style="color: var(--primary)"></i>
      {{ title }}
    </div>
    <div ref="chatRef" class="aich">
      <div v-for="(message, index) in messages" :key="`${message.role}-${index}`" class="aim" :class="message.role">
        {{ message.text }}
      </div>
    </div>
    <div class="aiin">
      <input v-model="input" :placeholder="placeholder" @keydown.enter="send" />
      <button class="aisend" type="button" aria-label="发送" @click="send">
        <i class="ti ti-send"></i>
      </button>
    </div>
  </div>
</template>

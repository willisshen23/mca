<script setup>
import { nextTick, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useAnalysisStore } from '../../stores/analysisStore';

const store = useAnalysisStore();
const router = useRouter();
const open = ref(false);
const input = ref('');
const chatRef = ref(null);

function toggle() {
  open.value = !open.value;
}

function send() {
  const value = input.value.trim();
  if (!value) return;
  store.addFloatingMessage('usr', value);
  input.value = '';
  const reply = handleAssistantCommand(value);
  window.setTimeout(() => {
    store.addFloatingMessage('ai', reply);
  }, 380);
}

function handleAssistantCommand(message) {
  if (message.includes('线上')) {
    store.setAnalysisType('online', true);
    router.push({ name: 'source', params: { type: 'online' } });
    return '已切换至线上活动。';
  }
  if (message.includes('线下')) {
    store.setAnalysisType('offline', true);
    router.push({ name: 'source', params: { type: 'offline' } });
    return '已切换至线下活动。';
  }
  if (message.includes('SKILL') || message.includes('skill') || message.includes('技能')) {
    router.push({ name: 'skills' });
    return '已跳转至 SKILL 技能管理页。';
  }
  if (message.includes('模板')) {
    return '活动分析数据模板入口已收到，可继续在首页选择数据模板卡片。';
  }
  if (message.includes('本月')) {
    return '已理解“本月”筛选意图，当前可查看首页统计与历史分析列表。';
  }
  return '收到，正在处理您的指令...';
}

watch(
  () => store.state.floatingMessages.length,
  async () => {
    await nextTick();
    if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight;
  },
  { immediate: true }
);
</script>

<template>
  <div class="fab">
    <div class="drawer" :class="{ open }">
      <div class="drh">
        <span>
          <i class="ti ti-message-circle" style="color: var(--primary); font-size: 14px" aria-hidden="true"></i>
          活动分析助手
        </span>
        <button class="drclose" type="button" aria-label="关闭活动分析助手" @click="toggle">
          <i class="ti ti-x" aria-hidden="true"></i>
        </button>
      </div>
      <div ref="chatRef" class="drb">
        <div v-for="(message, index) in store.state.floatingMessages" :key="index" class="drm" :class="message.role">
          {{ message.text }}
        </div>
      </div>
      <div class="drin">
        <input v-model="input" placeholder="输入指令..." @keydown.enter="send" />
        <button class="drsb" type="button" aria-label="发送" @click="send">
          <i class="ti ti-send"></i>
        </button>
      </div>
    </div>
    <button class="fabbtn" type="button" aria-label="打开活动分析助手" @click="toggle">
      <i class="ti ti-message-circle"></i>
    </button>
  </div>
</template>

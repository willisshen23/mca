<script setup>
import { computed, onMounted, ref } from 'vue';
import { fetchSkills } from '../../api/skills';
import { useAnalysisStore } from '../../stores/analysisStore';

const emit = defineEmits(['add', 'loaded']);
const store = useAnalysisStore();
const skills = ref([]);
const loading = ref(false);
const error = ref('');

const addedNames = computed(() => new Set(store.state.canvasComps.map((item) => item.name)));

const groupedSkills = computed(() => {
  const groups = new Map();
  skills.value.forEach((skill) => {
    if (!groups.has(skill.cat)) groups.set(skill.cat, []);
    groups.get(skill.cat).push(skill);
  });
  return Array.from(groups, ([cat, skills]) => ({ cat, skills }));
});

async function loadSkills() {
  loading.value = true;
  error.value = '';
  try {
    skills.value = await fetchSkills();
    emit('loaded', skills.value);
  } catch (err) {
    error.value = err.message || 'SKILL列表加载失败';
  } finally {
    loading.value = false;
  }
}

function dragStart(event, skill) {
  if (addedNames.value.has(skill.name)) {
    event.preventDefault();
    return;
  }
  const payload = JSON.stringify(skill);
  event.dataTransfer.setData('application/json', payload);
  event.dataTransfer.setData('text/plain', payload);
  event.dataTransfer.effectAllowed = 'copy';
}

function tryAdd(skill) {
  if (addedNames.value.has(skill.name)) return;
  emit('add', skill);
}

onMounted(loadSkills);
</script>

<template>
  <aside class="sklib">
    <div style="font-size: 12px; font-weight: 600; padding: 4px 6px; margin-bottom: 6px">
      <i class="ti ti-apps"></i> SKILL组件库（拖拽或双击添加）
    </div>
    <div v-if="loading" class="empty-canvas-hint" style="padding: 14px 8px">正在加载 SKILL...</div>
    <div v-else-if="error" class="empty-canvas-hint" style="padding: 14px 8px; color: var(--danger)">
      {{ error }}
    </div>
    <div v-for="group in groupedSkills" :key="group.cat" class="skgrp">
      <div class="skgrpn"><i class="ti ti-folder"></i> {{ group.cat }}</div>
      <div
        v-for="skill in group.skills"
        :key="skill.name"
        class="skcard"
        :class="{ added: addedNames.has(skill.name) }"
        :draggable="!addedNames.has(skill.name)"
        @dragstart="dragStart($event, skill)"
        @dblclick="tryAdd(skill)"
      >
        <div class="skcn">
          {{ skill.name }}
          <span v-if="addedNames.has(skill.name)" class="skadded"><i class="ti ti-check"></i> 已添加</span>
        </div>
        <div class="skcd">{{ skill.desc }} · 已应用 {{ skill.useCnt || 0 }} 次</div>
      </div>
    </div>
    <div v-if="!loading && !error && groupedSkills.length === 0" class="empty-canvas-hint" style="padding: 14px 8px">
      暂无可用 SKILL
    </div>
  </aside>
</template>

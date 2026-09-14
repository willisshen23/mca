<script setup>
import { ref } from 'vue';
import { useAnalysisStore } from '../../stores/analysisStore';

const store = useAnalysisStore();
const dragSourceIndex = ref(null);
const dragOverIndex = ref(null);

function startInternalDrag(event, index) {
  if (event.target.closest('.cbtn')) {
    event.preventDefault();
    return;
  }
  dragSourceIndex.value = index;
  event.dataTransfer.setData('text/plain', 'internal-sort');
  event.dataTransfer.effectAllowed = 'move';
}

function dropOnCanvas(event, targetIndex = null) {
  event.preventDefault();
  event.stopPropagation();

  if (dragSourceIndex.value !== null && targetIndex !== null) {
    store.reorderCanvasSkill(dragSourceIndex.value, targetIndex);
    dragSourceIndex.value = null;
    dragOverIndex.value = null;
    return;
  }

  const skill = readSkillFromDrop(event);
  if (skill?.name && skill?.cat) {
    store.addCanvasSkill(skill);
  }
  dragSourceIndex.value = null;
  dragOverIndex.value = null;
}

function readSkillFromDrop(event) {
  const json = event.dataTransfer.getData('application/json') || event.dataTransfer.getData('text/plain');
  if (!json || json === 'internal-sort') return null;
  try {
    return JSON.parse(json);
  } catch {
    return null;
  }
}
</script>

<template>
  <section class="canvas" @dragover.prevent @drop="dropOnCanvas">
    <div style="font-size: 11px; color: var(--t3); text-align: center; padding: 6px 0; border-bottom: 1px solid var(--border)">
      <i class="ti ti-cpu" style="color: var(--primary)"></i>
      拖拽排序 | 双击左侧库添加 | 上移下移按钮
    </div>
    <div class="canvas-list">
      <div v-if="store.state.canvasComps.length === 0" class="empty-canvas-hint">
        <i class="ti ti-click"></i> 暂无分析组件，请从左侧拖拽或双击添加 SKILL
      </div>
      <div
        v-for="(skill, index) in store.state.canvasComps"
        :key="`${skill.name}-${index}`"
        class="cc"
        :class="{ 'drag-over': dragOverIndex === index }"
        draggable="true"
        @dragstart="startInternalDrag($event, index)"
        @dragend="dragSourceIndex = null; dragOverIndex = null"
        @dragover.prevent.stop="dragOverIndex = index"
        @dragleave="dragOverIndex = null"
        @drop="dropOnCanvas($event, index)"
      >
        <i class="ti ti-grip-vertical dh"></i>
        <div class="ci">
          <div class="cn">{{ skill.name }}</div>
          <div class="cc2"><span class="tag tb" style="font-size: 11px">{{ skill.cat }}</span></div>
        </div>
        <div class="ca">
          <button class="cbtn" type="button" title="上移" @click.stop="store.moveCanvasSkill(index, -1)">
            <i class="ti ti-arrow-up"></i>
          </button>
          <button class="cbtn" type="button" title="下移" @click.stop="store.moveCanvasSkill(index, 1)">
            <i class="ti ti-arrow-down"></i>
          </button>
          <button class="cbtn del" type="button" title="删除" @click.stop="store.removeCanvasSkill(index)">×</button>
        </div>
      </div>
    </div>
  </section>
</template>

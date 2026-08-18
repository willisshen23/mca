<script setup>
import { computed, ref } from 'vue';
import { onlineActivities } from '../../data/mockData';
import { useAnalysisStore } from '../../stores/analysisStore';
import { activityStatusTone, displayActivityStatus, displayActivityType } from '../../utils/activityDictionaries.js';

const store = useAnalysisStore();
const keyword = ref('');
const globalStart = ref('2024-01-01');
const globalEnd = ref('2024-04-30');
const selectedCount = store.selectedCount;

const filteredActivities = computed(() => (
  onlineActivities.filter((activity) => activity.name.includes(keyword.value.trim()))
));

const allVisibleChecked = computed(() => (
  filteredActivities.value.length > 0
  && filteredActivities.value.every((activity) => store.state.selectedActivityNames.has(activity.name))
));

function toggleAllVisible(checked) {
  if (checked) {
    filteredActivities.value.forEach((activity) => store.state.selectedActivityNames.add(activity.name));
  } else {
    filteredActivities.value.forEach((activity) => store.state.selectedActivityNames.delete(activity.name));
  }
}

function selectAllVisible() {
  toggleAllVisible(true);
}

function clearAllVisible() {
  toggleAllVisible(false);
}

function statusClass(status) {
  const tone = activityStatusTone(status);
  if (tone === 'closed') return 'tgr';
  if (tone === 'active') return 'tg';
  return 'to';
}
</script>

<template>
  <section class="sc">
    <div class="sh">
      <i class="ti ti-table" style="color: var(--primary)"></i>
      <span class="stitle">存量线上活动选择</span>
      <span style="margin-left: auto; font-size: 11px; color: var(--t3)">勾选至少 1 个活动后可进入下一步</span>
    </div>
    <div class="itip">
      <i class="ti ti-info-circle"></i>
      从存量线上活动中选择分析对象，统计时间自动取所选活动时间合集。
    </div>
    <div class="frow">
      <div class="fg">
        <label class="flabel">活动名称搜索</label>
        <input v-model="keyword" class="fi" placeholder="输入关键词..." />
      </div>
      <div class="fg">
        <label class="flabel">起始日期</label>
        <input v-model="globalStart" class="fi" type="date" />
      </div>
      <div class="fg">
        <label class="flabel">截止日期</label>
        <input v-model="globalEnd" class="fi" type="date" />
      </div>
      <div class="fg select-actions">
        <label class="flabel">批量选择</label>
        <div class="select-action-row">
          <button class="btn sm ghost" type="button" :disabled="filteredActivities.length === 0 || allVisibleChecked" @click="selectAllVisible">
            全选
          </button>
          <button class="btn sm" type="button" :disabled="filteredActivities.length === 0" @click="clearAllVisible">
            全不选
          </button>
        </div>
      </div>
    </div>
    <div class="table-scroll">
      <table class="tbl">
        <thead>
          <tr>
            <th style="width: 36px">
              <input class="ck" type="checkbox" :checked="allVisibleChecked" @change="toggleAllVisible($event.target.checked)" />
            </th>
            <th>活动名称</th>
            <th>类型</th>
            <th>起止时间</th>
            <th>活动目标</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="activity in filteredActivities"
            :key="activity.name"
            :class="{ sel: store.state.selectedActivityNames.has(activity.name) }"
            style="cursor: pointer"
            @click="store.toggleActivity(activity.name)"
          >
            <td>
              <input
                class="ck"
                type="checkbox"
                :checked="store.state.selectedActivityNames.has(activity.name)"
                @click.stop="store.toggleActivity(activity.name)"
              />
            </td>
            <td :style="{ fontWeight: store.state.selectedActivityNames.has(activity.name) ? 500 : 400 }">{{ activity.name }}</td>
            <td><span class="tag tb">{{ displayActivityType(activity.type, activity.status) || activity.type }}</span></td>
            <td>{{ activity.start }} ~ {{ activity.end }}</td>
            <td>{{ activity.goal }}</td>
            <td><span class="tag" :class="statusClass(activity.status)">{{ displayActivityStatus(activity.status) || activity.status }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="selectedCount > 0" class="selbar">
      <i class="ti ti-check-circle"></i>
      <span>已选 {{ selectedCount }} 个活动</span>
      <span style="margin-left: auto; font-size: 11px">统计时间自动取所选活动时间合集</span>
    </div>
  </section>
</template>

<style scoped>
.select-actions {
  flex: 0 0 auto;
  min-width: 150px;
}

.select-action-row {
  display: flex;
  gap: 8px;
}
</style>

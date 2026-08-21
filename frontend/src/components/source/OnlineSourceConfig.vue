<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { fetchOnlineActivities } from '../../api/activities';
import { MAX_SELECTED_ACTIVITIES, useAnalysisStore } from '../../stores/analysisStore';
import { activityStatusTone, displayActivityStatus, displayActivityType } from '../../utils/activityDictionaries.js';

const props = defineProps({
  // /main 独立页将已选回显条移到页面底部按钮栏，此处可关闭组件内置的
  showSelectedBar: { type: Boolean, default: true }
});

const store = useAnalysisStore();
const keyword = ref('');
const globalStart = ref('');
const globalEnd = ref('');
const selectedCount = store.selectedCount;

const activities = ref([]);
const loading = ref(false);
const loadError = ref('');

async function loadActivities() {
  loading.value = true;
  loadError.value = '';
  try {
    activities.value = await fetchOnlineActivities({
      startDate: globalStart.value,
      endDate: globalEnd.value
    });
  } catch (error) {
    loadError.value = error.message || '活动列表加载失败';
  } finally {
    loading.value = false;
  }
}

onMounted(loadActivities);

// 日期范围变化时重新查询活动列表
watch([globalStart, globalEnd], () => {
  if (globalStart.value && globalEnd.value && globalStart.value > globalEnd.value) {
    loadError.value = '起始日期不能晚于截止日期';
    return;
  }
  loadActivities();
});

const filteredActivities = computed(() => (
  activities.value.filter((activity) => activity.name.includes(keyword.value.trim()))
));

const limitReached = computed(() => selectedCount.value >= MAX_SELECTED_ACTIVITIES);

function isActivitySelected(activity) {
  return store.state.selectedActivityNames.has(activity.name);
}

function isActivityDisabled(activity) {
  return limitReached.value && !isActivitySelected(activity);
}

function handleRowClick(activity) {
  if (isActivityDisabled(activity)) return;
  store.toggleActivity(activity.name);
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
      <span style="margin-left: auto; font-size: 11px; color: var(--t3)">勾选至少 1 个活动后可进入下一步，最多选择 {{ MAX_SELECTED_ACTIVITIES }} 个</span>
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
    </div>
    <div class="table-scroll">
      <table class="tbl">
        <thead>
          <tr>
            <th style="width: 36px"></th>
            <th>活动名称</th>
            <th>类型</th>
            <th>起止时间</th>
            <th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="5" class="tbl-tip">活动列表加载中...</td>
          </tr>
          <tr v-else-if="loadError">
            <td colspan="5" class="tbl-tip">
              {{ loadError }}
              <button class="btn sm ghost" type="button" style="margin-left: 8px" @click="loadActivities">重试</button>
            </td>
          </tr>
          <tr v-else-if="filteredActivities.length === 0">
            <td colspan="5" class="tbl-tip">暂无匹配的线上活动</td>
          </tr>
          <tr
            v-for="activity in filteredActivities"
            :key="activity.name"
            :class="{ sel: isActivitySelected(activity), 'row-disabled': isActivityDisabled(activity) }"
            :style="{ cursor: isActivityDisabled(activity) ? 'not-allowed' : 'pointer' }"
            @click="handleRowClick(activity)"
          >
            <td>
              <input
                class="ck"
                type="checkbox"
                :checked="isActivitySelected(activity)"
                :disabled="isActivityDisabled(activity)"
                @click.stop="handleRowClick(activity)"
              />
            </td>
            <td :style="{ fontWeight: isActivitySelected(activity) ? 500 : 400 }">{{ activity.name }}</td>
            <td><span class="tag tb">{{ displayActivityType(activity.type, activity.status) || activity.type }}</span></td>
            <td>{{ activity.start }} ~ {{ activity.end }}</td>
            <td><span class="tag" :class="statusClass(activity.status)">{{ displayActivityStatus(activity.status) || activity.status }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="props.showSelectedBar && selectedCount > 0" class="selbar">
      <i class="ti ti-check-circle"></i>
      <span>已选 {{ selectedCount }}/{{ MAX_SELECTED_ACTIVITIES }} 个活动</span>
      <span style="margin-left: auto; font-size: 11px">统计时间自动取所选活动时间合集</span>
    </div>
  </section>
</template>

<style scoped>
.tbl-tip {
  text-align: center;
  color: var(--t3);
  font-size: 12px;
  padding: 24px 0;
}

.tbl tbody tr.row-disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
</style>

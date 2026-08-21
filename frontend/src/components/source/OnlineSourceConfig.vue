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

// 分页：上游接口无总数，靠 hasMore 判断是否还有下一页
const PAGE_SIZES = [10, 20, 50, 100];
const page = ref(1);
const pageSize = ref(20);
const hasMore = ref(false);

async function loadActivities() {
  loading.value = true;
  loadError.value = '';
  try {
    const result = await fetchOnlineActivities({
      keyword: keyword.value.trim(),
      startDate: globalStart.value,
      endDate: globalEnd.value,
      page: page.value,
      pageSize: pageSize.value
    });
    activities.value = result.activities;
    hasMore.value = result.hasMore;
    // 过滤条件变化后若当前页已无数据且不是第一页，回退到第一页重查
    if (result.activities.length === 0 && page.value > 1) {
      page.value = 1;
      await loadActivities();
    }
  } catch (error) {
    loadError.value = error.message || '活动列表加载失败';
  } finally {
    loading.value = false;
  }
}

onMounted(loadActivities);

// 关键词输入防抖，避免每个字符都触发一次查询
let keywordTimer = null;
watch(keyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer);
  keywordTimer = setTimeout(() => {
    page.value = 1;
    loadActivities();
  }, 300);
});

// 日期范围变化时重新查询活动列表
watch([globalStart, globalEnd], () => {
  if (globalStart.value && globalEnd.value && globalStart.value > globalEnd.value) {
    loadError.value = '起始日期不能晚于截止日期';
    return;
  }
  page.value = 1;
  loadActivities();
});

function changePage(next) {
  if (next < 1 || (next > page.value && !hasMore.value)) return;
  page.value = next;
  loadActivities();
}

function changePageSize() {
  page.value = 1;
  loadActivities();
}

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
          <tr v-else-if="activities.length === 0">
            <td colspan="5" class="tbl-tip">暂无匹配的线上活动</td>
          </tr>
          <tr
            v-for="activity in activities"
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
    <div class="act-pagination">
      <select v-model.number="pageSize" class="page-size" :disabled="loading" @change="changePageSize">
        <option v-for="size in PAGE_SIZES" :key="size" :value="size">{{ size }} 条/页</option>
      </select>
      <button class="pgb" type="button" :disabled="page <= 1 || loading" @click="changePage(page - 1)">
        <i class="ti ti-chevron-left"></i>
      </button>
      <span class="page-current">第 {{ page }} 页</span>
      <button class="pgb" type="button" :disabled="!hasMore || loading" @click="changePage(page + 1)">
        <i class="ti ti-chevron-right"></i>
      </button>
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

.act-pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 10px;
  color: var(--t2);
  font-size: 12px;
}

.page-size {
  height: 28px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: #fff;
  color: var(--t1);
  padding: 0 8px;
  outline: none;
}

.page-current {
  min-width: 52px;
  text-align: center;
  color: var(--t2);
}

.pgb:disabled {
  cursor: not-allowed;
  opacity: 0.45;
  pointer-events: none;
}
</style>

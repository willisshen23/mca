<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import TopBar from '../components/layout/TopBar.vue';
import {
  downloadUsageDetails,
  fetchUsageSummary,
  recordUsageEvent
} from '../api/usageDashboard';
import { useAnalysisStore } from '../stores/analysisStore';

const route = useRoute();
const router = useRouter();
const store = useAnalysisStore();
const days = ref(30);
const loading = ref(true);
const error = ref('');
const summary = ref(null);
const exporting = ref(false);
const trendChartType = ref('line');
const tokenChartType = ref('line');

const metricDefinitions = [
  { key: 'visitors', label: '到访用户', icon: 'ti-users', tone: 'blue' },
  { key: 'reports', label: '生成报告', icon: 'ti-file-analytics', tone: 'purple' },
  { key: 'conversations', label: '新建会话', icon: 'ti-messages', tone: 'green' },
  { key: 'turns', label: '对话轮次', icon: 'ti-message-circle-2', tone: 'orange' }
];

const secondaryMetrics = computed(() => {
  const metrics = summary.value?.metrics || {};
  return [
    { label: '页面访问', value: metrics.page_views?.value || 0, hint: '含重复访问' },
    { label: '访问机构', value: metrics.organizations?.value || 0, hint: '按机构编号去重' },
    { label: '会话成功率', value: `${metrics.success_rate || 0}%`, hint: '成功完成的对话轮次' },
    { label: '平均响应耗时', value: formatDuration(metrics.avg_duration_seconds), hint: '已完成轮次平均值' }
  ];
});

const llmMetrics = computed(() => {
  const usage = summary.value?.llm_usage || {};
  return [
    {
      label: '大模型调用',
      value: formatNumber(usage.calls?.value),
      hint: changeText(usage.calls),
      icon: 'ti-api',
      tone: 'blue'
    },
    {
      label: 'Token 总消耗',
      value: formatCompactNumber(usage.total_tokens?.value),
      hint: changeText(usage.total_tokens),
      icon: 'ti-coin',
      tone: 'purple'
    },
    {
      label: '单次平均 Token',
      value: formatCompactNumber(usage.avg_tokens_per_call),
      hint: '按大模型调用次数计算',
      icon: 'ti-chart-arrows-vertical',
      tone: 'green'
    },
    {
      label: '平均执行耗时',
      value: formatMilliseconds(usage.avg_time_spent_ms),
      hint: '从请求开始到模型返回',
      icon: 'ti-clock',
      tone: 'orange'
    },
    {
      label: '调用成功率',
      value: `${Number(usage.success_rate || 0).toFixed(1)}%`,
      hint: `${formatNumber(usage.successful_calls)} 成功 / ${formatNumber(usage.failed_calls)} 失败`,
      icon: 'ti-circle-check',
      tone: 'cyan'
    }
  ];
});

const tokenTrendChart = computed(() => {
  const rows = summary.value?.llm_usage?.trend || [];
  const width = 720;
  const height = 140;
  const max = Math.max(...rows.map((item) => Number(item.tokens || 0)), 1);
  const x = (index) => rows.length <= 1 ? width / 2 : (index * width) / (rows.length - 1);
  const points = rows.map((item, index) => {
    const y = height - (Number(item.tokens || 0) / max) * (height - 10);
    return {
      date: item.date,
      tokens: Number(item.tokens || 0),
      calls: Number(item.calls || 0),
      x: x(index),
      y
    };
  });
  return {
    rows,
    hasData: points.some((item) => item.tokens > 0),
    max,
    height,
    points,
    polyline: points.map((item) => `${item.x.toFixed(1)},${item.y.toFixed(1)}`).join(' '),
    area: points.length
      ? `0,${height} ${points.map((item) => `${item.x.toFixed(1)},${item.y.toFixed(1)}`).join(' ')} ${width},${height}`
      : ''
  };
});

const tokenTrendBars = computed(() => {
  const rows = tokenTrendChart.value.rows;
  const width = 720;
  const height = tokenTrendChart.value.height;
  const max = tokenTrendChart.value.max;
  const groupWidth = rows.length ? width / rows.length : width;
  const barWidth = Math.max(Math.min(groupWidth * 0.58, 24), 2);
  return rows.map((item, index) => {
    const tokens = Number(item.tokens || 0);
    const barHeight = tokens ? Math.max(tokens / max * (height - 10), 2) : 0;
    return {
      date: item.date,
      tokens,
      calls: Number(item.calls || 0),
      x: index * groupWidth + (groupWidth - barWidth) / 2,
      y: height - barHeight,
      width: barWidth,
      height: barHeight
    };
  });
});

const tokenDateLabels = computed(() => {
  const rows = tokenTrendChart.value.rows;
  if (!rows.length) return [];
  const indexes = [...new Set([0, Math.floor((rows.length - 1) / 2), rows.length - 1])];
  return indexes.map((index) => ({
    label: rows[index].date.slice(5).replace('-', '/'),
    left: rows.length <= 1 ? 50 : (index * 100) / (rows.length - 1)
  }));
});

const trendPoints = computed(() => {
  const rows = summary.value?.trend || [];
  const width = 720;
  const height = 180;
  const allValues = rows.flatMap((item) => [item.visitors, item.conversations, item.reports]);
  const max = Math.max(...allValues, 1);
  const x = (index) => rows.length <= 1 ? 0 : (index * width) / (rows.length - 1);
  const points = (key) => rows.map((item, index) => {
    const y = height - (Number(item[key] || 0) / max) * (height - 12);
    return `${x(index).toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  return {
    visitors: points('visitors'),
    conversations: points('conversations'),
    reports: points('reports'),
    max
  };
});

const trendBars = computed(() => {
  const rows = summary.value?.trend || [];
  const width = 720;
  const height = 180;
  const keys = ['visitors', 'conversations', 'reports'];
  const colors = {
    visitors: '#165dff',
    conversations: '#00b578',
    reports: '#8d5ce6'
  };
  const max = trendPoints.value.max || 1;
  const groupWidth = rows.length ? width / rows.length : width;
  const barGap = Math.min(1.5, groupWidth * 0.08);
  const barWidth = Math.max((groupWidth - barGap * 4) / keys.length, 0.8);
  return rows.flatMap((item, rowIndex) => keys.map((key, keyIndex) => {
    const value = Number(item[key] || 0);
    const barHeight = value ? Math.max(value / max * (height - 12), 1.5) : 0;
    const occupiedWidth = barWidth * keys.length + barGap * (keys.length - 1);
    return {
      id: `${item.date}-${key}`,
      x: rowIndex * groupWidth + (groupWidth - occupiedWidth) / 2 + keyIndex * (barWidth + barGap),
      y: height - barHeight,
      width: barWidth,
      height: barHeight,
      color: colors[key]
    };
  }));
});

const dateLabels = computed(() => {
  const rows = summary.value?.trend || [];
  if (!rows.length) return [];
  const indexes = [...new Set([0, Math.floor((rows.length - 1) / 2), rows.length - 1])];
  return indexes.map((index) => ({
    label: rows[index].date.slice(5).replace('-', '/'),
    left: rows.length <= 1 ? 0 : (index * 100) / (rows.length - 1)
  }));
});

const maxOrganizationViews = computed(() => {
  const organizations = summary.value?.organizations || [];
  return Math.max(...organizations.map((item) => Number(item.page_views || 0)), 1);
});

function formatNumber(value) {
  return new Intl.NumberFormat('zh-CN').format(Number(value || 0));
}

function formatCompactNumber(value) {
  const number = Number(value || 0);
  if (number < 10000) return formatNumber(Math.round(number));
  return new Intl.NumberFormat('zh-CN', {
    notation: 'compact',
    maximumFractionDigits: 1
  }).format(number);
}

function formatDuration(seconds) {
  const value = Number(seconds || 0);
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)} 秒`;
  return `${(value / 60).toFixed(1)} 分钟`;
}

function formatMilliseconds(milliseconds) {
  const value = Number(milliseconds || 0);
  if (value < 1000) return `${Math.round(value)} ms`;
  return formatDuration(value / 1000);
}

function changeText(metric) {
  const change = metric?.change_pct;
  if (change === null || change === undefined) return '暂无上期数据';
  if (change === 0) return '与上期持平';
  return `${change > 0 ? '↑' : '↓'} ${Math.abs(change)}% 较上期`;
}

function sourceFromPage() {
  const querySource = String(route.query.source || route.query.utm_source || '').trim();
  if (querySource) return querySource.slice(0, 80);
  if (!document.referrer) return '直接访问';
  try {
    return new URL(document.referrer).hostname || '站内跳转';
  } catch {
    return '站内跳转';
  }
}

async function loadSummary() {
  loading.value = true;
  error.value = '';
  try {
    summary.value = await fetchUsageSummary(days.value);
  } catch (err) {
    error.value = err.message || '使用量数据加载失败';
  } finally {
    loading.value = false;
  }
}

async function exportDetails() {
  if (exporting.value) return;
  exporting.value = true;
  error.value = '';
  try {
    await downloadUsageDetails(days.value);
  } catch (err) {
    error.value = err.message || '使用明细导出失败';
  } finally {
    exporting.value = false;
  }
}

async function start(type) {
  store.setAnalysisType(type, true);
  router.push({ name: 'source', params: { type } });
}

async function enterChat() {
  router.push({ name: 'chat-ui' });
}

onMounted(async () => {
  try {
    await recordUsageEvent('home_view', { source: sourceFromPage() });
  } catch {
    // Dashboard remains useful even when event collection is temporarily unavailable.
  }
  await loadSummary();
});
</script>

<template>
  <div class="page usage-home">
    <TopBar title="活动分析助手">
      <span class="home-top-label">运营使用概览</span>
    </TopBar>

    <div class="content usage-content">
      <section class="usage-hero">
        <div>
          <span class="hero-eyebrow">AI 活动分析工作台</span>
          <h2>让每一次分析都有迹可循</h2>
          <p>从用户到访、创建会话到报告产出，集中掌握平台使用情况与转化效率。</p>
        </div>
        <button type="button" class="hero-action" @click="enterChat">
          <i class="ti ti-sparkles"></i>
          发起智能分析
        </button>
      </section>

      <section class="usage-toolbar">
        <div>
          <h3>使用量概览</h3>
          <p v-if="summary">{{ summary.period.start }} 至 {{ summary.period.end }}</p>
          <p v-else>统计真实业务使用数据</p>
        </div>
        <div class="usage-toolbar-actions">
          <button
            type="button"
            class="usage-export-button"
            :disabled="exporting"
            @click="exportDetails"
          >
            <i :class="['ti', exporting ? 'ti-loader-2' : 'ti-file-export']"></i>
            {{ exporting ? '正在导出' : '导出明细' }}
          </button>
          <div class="period-tabs" aria-label="统计周期">
            <button
              v-for="option in [7, 30, 90]"
              :key="option"
              type="button"
              :class="{ active: days === option }"
              @click="days = option; loadSummary()"
            >
              近 {{ option }} 天
            </button>
            <button type="button" class="refresh-button" title="刷新" @click="loadSummary">
              <i class="ti ti-refresh"></i>
            </button>
          </div>
        </div>
      </section>

      <div v-if="error" class="usage-error">
        <i class="ti ti-alert-circle"></i>
        {{ error }}
        <button type="button" @click="loadSummary">重试</button>
      </div>

      <section class="metric-grid" :aria-busy="loading">
        <article v-for="definition in metricDefinitions" :key="definition.key" class="metric-card">
          <div :class="['metric-icon', definition.tone]">
            <i :class="['ti', definition.icon]"></i>
          </div>
          <div class="metric-label">{{ definition.label }}</div>
          <div class="metric-value">
            {{ loading && !summary ? '—' : formatNumber(summary?.metrics?.[definition.key]?.value) }}
          </div>
          <div
            :class="[
              'metric-change',
              { down: (summary?.metrics?.[definition.key]?.change_pct || 0) < 0 }
            ]"
          >
            {{ changeText(summary?.metrics?.[definition.key]) }}
          </div>
        </article>
      </section>

      <section class="secondary-strip">
        <div v-for="item in secondaryMetrics" :key="item.label" class="secondary-item">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <small>{{ item.hint }}</small>
        </div>
      </section>

      <section class="llm-usage-panel" :aria-busy="loading">
        <div class="llm-usage-heading">
          <div>
            <span class="llm-usage-eyebrow">LLM USAGE</span>
            <h3>大模型调用统计</h3>
          </div>
          <span>场景：活动分析助手</span>
        </div>
        <div class="llm-metric-grid">
          <article v-for="item in llmMetrics" :key="item.label" class="llm-metric-item">
            <div :class="['llm-metric-icon', item.tone]">
              <i :class="['ti', item.icon]"></i>
            </div>
            <div class="llm-metric-copy">
              <span>{{ item.label }}</span>
              <strong>{{ loading && !summary ? '—' : item.value }}</strong>
              <small>{{ item.hint }}</small>
            </div>
          </article>
        </div>
        <div class="token-trend-block">
          <div class="token-trend-heading">
            <div>
              <h4>Token 总量变化</h4>
              <p>每日大模型调用的 Token 消耗总量</p>
            </div>
            <div class="chart-type-switch" aria-label="Token 趋势图类型">
              <button
                type="button"
                :class="{ active: tokenChartType === 'line' }"
                title="折线图"
                @click="tokenChartType = 'line'"
              >
                <i class="ti ti-chart-line"></i>
              </button>
              <button
                type="button"
                :class="{ active: tokenChartType === 'bar' }"
                title="柱状图"
                @click="tokenChartType = 'bar'"
              >
                <i class="ti ti-chart-bar"></i>
              </button>
            </div>
          </div>
          <div v-if="tokenTrendChart.hasData" class="token-trend-chart">
            <div class="token-gridline token-top">
              <span>{{ formatCompactNumber(tokenTrendChart.max) }}</span>
            </div>
            <div class="token-gridline token-middle">
              <span>{{ formatCompactNumber(tokenTrendChart.max / 2) }}</span>
            </div>
            <div class="token-gridline token-bottom"><span>0</span></div>
            <svg
              viewBox="0 0 720 140"
              preserveAspectRatio="none"
              role="img"
              aria-label="每日 Token 总量趋势"
            >
              <template v-if="tokenChartType === 'line'">
                <polygon class="token-trend-area" :points="tokenTrendChart.area" />
                <polyline class="token-trend-line" :points="tokenTrendChart.polyline" />
                <circle
                  v-for="point in tokenTrendChart.points.filter((item) => item.tokens > 0)"
                  :key="point.date"
                  class="token-trend-point"
                  :cx="point.x"
                  :cy="point.y"
                  r="3"
                >
                  <title>{{ point.date }}：{{ formatNumber(point.tokens) }} Token，{{ point.calls }} 次调用</title>
                </circle>
              </template>
              <template v-else>
                <rect
                  v-for="bar in tokenTrendBars"
                  :key="bar.date"
                  class="token-trend-bar"
                  :x="bar.x"
                  :y="bar.y"
                  :width="bar.width"
                  :height="bar.height"
                  rx="2"
                >
                  <title>{{ bar.date }}：{{ formatNumber(bar.tokens) }} Token，{{ bar.calls }} 次调用</title>
                </rect>
              </template>
            </svg>
            <span
              v-for="item in tokenDateLabels"
              :key="item.label"
              class="token-date-label"
              :style="{ left: `${item.left}%` }"
            >
              {{ item.label }}
            </span>
          </div>
          <div v-else class="token-trend-empty">统计周期内暂无 Token 消耗数据</div>
        </div>
      </section>

      <section class="insight-grid">
        <article class="insight-card trend-card">
          <div class="card-heading">
            <div>
              <h3>使用趋势</h3>
              <p>每日独立到访、会话与报告产出</p>
            </div>
            <div class="trend-heading-tools">
              <div class="chart-type-switch" aria-label="趋势图类型">
                <button
                  type="button"
                  :class="{ active: trendChartType === 'line' }"
                  title="折线图"
                  @click="trendChartType = 'line'"
                >
                  <i class="ti ti-chart-line"></i>
                </button>
                <button
                  type="button"
                  :class="{ active: trendChartType === 'bar' }"
                  title="柱状图"
                  @click="trendChartType = 'bar'"
                >
                  <i class="ti ti-chart-bar"></i>
                </button>
              </div>
              <div class="trend-legend">
                <span><i class="dot visitors"></i>到访用户</span>
                <span><i class="dot conversations"></i>新建会话</span>
                <span><i class="dot reports"></i>生成报告</span>
              </div>
            </div>
          </div>
          <div v-if="summary?.trend?.length" class="trend-chart">
            <div class="chart-gridline top"><span>{{ trendPoints.max }}</span></div>
            <div class="chart-gridline middle"><span>{{ Math.round(trendPoints.max / 2) }}</span></div>
            <div class="chart-gridline bottom"><span>0</span></div>
            <svg viewBox="0 0 720 180" preserveAspectRatio="none" role="img" aria-label="使用量趋势图">
              <template v-if="trendChartType === 'line'">
                <polyline class="trend-line visitors" :points="trendPoints.visitors" />
                <polyline class="trend-line conversations" :points="trendPoints.conversations" />
                <polyline class="trend-line reports" :points="trendPoints.reports" />
              </template>
              <template v-else>
                <rect
                  v-for="bar in trendBars"
                  :key="bar.id"
                  class="trend-bar"
                  :x="bar.x"
                  :y="bar.y"
                  :width="bar.width"
                  :height="bar.height"
                  :fill="bar.color"
                  rx="1"
                />
              </template>
            </svg>
            <span
              v-for="item in dateLabels"
              :key="item.label"
              class="date-label"
              :style="{ left: `${item.left}%` }"
            >
              {{ item.label }}
            </span>
          </div>
          <div v-else class="empty-insight">统计周期内暂无趋势数据</div>
        </article>

        <article class="insight-card organization-card">
          <div class="card-heading">
            <div>
              <h3>机构活跃度</h3>
              <p>按机构编号统计访问用户与访问次数</p>
            </div>
          </div>
          <div v-if="summary?.organizations?.length" class="organization-list">
            <div
              v-for="(item, index) in summary.organizations"
              :key="item.org_no"
              class="organization-row"
            >
              <span class="organization-rank">{{ index + 1 }}</span>
              <div class="organization-main">
                <div class="organization-meta">
                  <strong>{{ item.org_no }}</strong>
                  <span>{{ item.visitors }} 位用户 · {{ item.page_views }} 次访问</span>
                </div>
                <div class="organization-track">
                  <span
                    :style="{
                      width: `${Math.max(item.page_views * 100 / maxOrganizationViews, 4)}%`
                    }"
                  ></span>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="empty-organization">
            <i class="ti ti-building-community"></i>
            <span>统计周期内暂无机构访问数据</span>
          </div>
        </article>
      </section>

      <section class="entry-section">
        <div class="section-heading">
          <div>
            <h3>快速开始</h3>
            <p>选择适合的分析方式，快速进入工作流</p>
          </div>
        </div>
        <div class="hmcards">
          <button class="hmc" type="button" @click="start('online')">
            <div class="hmc-ic online"><i class="ti ti-device-desktop-analytics"></i></div>
            <div>
              <h4>线上活动分析</h4>
              <p>APP 推广、直播营销、线上理财等数字渠道活动分析</p>
            </div>
            <i class="ti ti-arrow-right entry-arrow"></i>
          </button>
          <button class="hmc" type="button" @click="start('offline')">
            <div class="hmc-ic offline"><i class="ti ti-building-store"></i></div>
            <div>
              <h4>线下活动分析</h4>
              <p>网点营销、户外推广、客户拜访等线下活动效果分析</p>
            </div>
            <i class="ti ti-arrow-right entry-arrow"></i>
          </button>
          <button class="hmc" type="button" @click="router.push({ name: 'templates' })">
            <div class="hmc-ic template"><i class="ti ti-layout-cards"></i></div>
            <div>
              <h4>活动分析模板</h4>
              <p>使用预置专项分析模板，更快完成标准化报告</p>
            </div>
            <i class="ti ti-arrow-right entry-arrow"></i>
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* 页面整体字体放大（仅 /main 首页看板） */
.home-top-label { font-size: 14px; }

.hero-eyebrow { font-size: 13px; }
.usage-hero h2 { font-size: 28px; }
.usage-hero p { font-size: 15px; }
.hero-action { font-size: 14px; }

.usage-toolbar h3, .card-heading h3, .section-heading h3 { font-size: 17px; }
.usage-toolbar p, .card-heading p, .section-heading p { font-size: 13px; }
.usage-export-button { font-size: 13px; }
.period-tabs button { font-size: 13px; }
.usage-error { font-size: 14px; }

.metric-label { font-size: 13px; }
.metric-value { font-size: 30px; }
.metric-change { font-size: 12px; }

.secondary-item span { font-size: 13px; }
.secondary-item strong { font-size: 19px; }
.secondary-item small { font-size: 11px; }

.llm-usage-heading h3 { font-size: 17px; }
.llm-usage-heading > span { font-size: 12px; }
.llm-usage-eyebrow { font-size: 10px; }
.llm-metric-copy span { font-size: 11px; }
.llm-metric-copy strong { font-size: 20px; }
.llm-metric-copy small { font-size: 10px; }

.token-trend-heading h4 { font-size: 14px; }
.token-trend-heading p { font-size: 11px; }
.token-gridline span { font-size: 10px; }
.token-date-label { font-size: 10px; }
.token-trend-empty { font-size: 12px; }

.trend-legend { font-size: 11px; }
.chart-gridline span { font-size: 11px; }
.date-label { font-size: 11px; }
.empty-insight { font-size: 13px; }

.organization-rank { font-size: 12px; }
.organization-meta strong { font-size: 13px; }
.organization-meta span { font-size: 11px; }
.empty-organization { font-size: 13px; }

.usage-home .hmc h4 { font-size: 15px; }
.usage-home .hmc p { font-size: 12px; }
</style>

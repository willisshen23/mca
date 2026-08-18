<script setup>
import { reportBars } from '../../data/mockData';
import { useAnalysisStore } from '../../stores/analysisStore';
import BarChartList from './BarChartList.vue';

const store = useAnalysisStore();
</script>

<template>
  <section class="rgrid">
    <div class="rcard">
      <div class="rcardt"><i class="ti ti-chart-bar"></i>核心KPI</div>
      <div class="krow">
        <div class="kpi"><div class="kpiv">28.6%</div><div class="kpil">参与率</div></div>
        <div class="kpi"><div class="kpiv">4.2%</div><div class="kpil">转化率</div></div>
        <div class="kpi"><div class="kpiv" style="color: #00B42A">136%</div><div class="kpil">目标达成</div></div>
      </div>
    </div>
    <div class="rcard">
      <div class="rcardt"><i class="ti ti-users"></i>客群分布</div>
      <BarChartList :items="reportBars.customers" />
    </div>
    <div class="rcard">
      <div class="rcardt"><i class="ti ti-activity"></i>渠道效果</div>
      <BarChartList :items="reportBars.channels" />
    </div>
    <div class="rcard">
      <div class="rcardt"><i class="ti ti-bulb"></i>AI洞察</div>
      <ul class="ins">
        <li class="insi g">APP渠道效率最高，建议加大高响应客群触达频次。</li>
        <li class="insi w">邮件营销 ROI 偏低，需优化内容与投放人群。</li>
        <li class="insi">当前框架包含 {{ store.state.canvasComps.length }} 个分析组件。</li>
      </ul>
    </div>
  </section>
</template>

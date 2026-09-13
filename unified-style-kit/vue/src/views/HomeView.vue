<!-- ==========================================================================
     FAB 统一风格 —— 首页（对应 njbank 的 src/views/HomeView.vue）
     --------------------------------------------------------------------------
     ⚠️ 功能与原版逐项一致，未新增也未删减：
        TopBar(title + 右侧说明) → hbanner → strow 4 个统计 → hmcards 3 张入口卡
     统计数值、卡片文案、点击行为（start('online') / start('offline') /
     跳转 templates）全部照搬原文件。

     视觉层改动全部由 assets/fab-theme.css 承担，本文件的 class 名一个没改，
     所以其实**你可以完全不用这个文件**：只要引入 fab-theme.css，原来的
     HomeView.vue 就已经是新风格了。这里放出来只是给出对照。
     ========================================================================== -->
<script setup>
import { useRouter } from 'vue-router';
import TopBar from '../components/layout/TopBar.vue';
import { useAnalysisStore } from '../stores/analysisStore';

const router = useRouter();
const store = useAnalysisStore();

function start(type) {
  store.setAnalysisType(type, true);
  router.push({ name: 'source', params: { type } });
}
</script>

<template>
  <div class="page">
    <TopBar title="营销智能分析系统">
      <span style="margin-left: auto; font-size: 12px; color: var(--t3)">银行 B 端营销分析平台</span>
    </TopBar>
    <div class="content">
      <section class="hbanner">
        <h2>营销智能活动分析</h2>
        <p>AI 驱动的银行营销活动深度分析，支持线上/线下活动数据，智能匹配 SKILL 组件，一键生成专业分析报告</p>
      </section>

      <section class="strow">
        <div class="sti">
          <div class="stn">128</div>
          <div class="stl">本月分析活动数</div>
          <div class="stc">↑ 12% 较上月</div>
        </div>
        <div class="sti">
          <div class="stn">36</div>
          <div class="stl">可用 SKILL 数量</div>
          <div class="stc">↑ 3 新增</div>
        </div>
        <div class="sti">
          <div class="stn">8</div>
          <div class="stl">活动分析模板</div>
          <div class="stc">↑ 2 新增</div>
        </div>
        <div class="sti">
          <div class="stn">52</div>
          <div class="stl">本月报告导出</div>
          <div class="stc">↑ 8%</div>
        </div>
      </section>

      <section class="hmcards">
        <button class="hmc" type="button" @click="start('online')">
          <div class="hmc-ic">
            <i class="ti ti-device-desktop-analytics"></i>
          </div>
          <h4>线上活动分析</h4>
          <p>APP 推广、直播营销、线上理财等数字渠道活动分析</p>
        </button>
        <button class="hmc" type="button" @click="start('offline')">
          <div class="hmc-ic">
            <i class="ti ti-building-store"></i>
          </div>
          <h4>线下活动分析</h4>
          <p>网点营销、户外推广、客户拜访等线下活动效果分析</p>
        </button>
        <button class="hmc" type="button" @click="router.push({ name: 'templates' })">
          <div class="hmc-ic">
            <i class="ti ti-layout-cards"></i>
          </div>
          <h4>活动分析模板</h4>
          <p>预置多活动分析、外呼活动等专项分析模板，快速启动</p>
        </button>
      </section>
    </div>
  </div>
</template>

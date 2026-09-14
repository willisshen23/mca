<script setup>
// /main 独立流程（数据源配置 → 组件编排 → 分析报告）三页共用的品牌横幅：
// 通栏渐变底 + 大标题，置于 TopBar 之上，仅 standalone 的 /main 页面使用。
defineProps({
  title: {
    type: String,
    default: '营销活动智能分析助手'
  },
  subtitle: {
    type: String,
    default: ''
  }
});
</script>

<template>
  <div class="main-hero">
    <div class="main-hero-text">
      <div class="main-hero-title">
        <i class="ti ti-sparkles"></i>
        <span>{{ title }}</span>
      </div>
      <div v-if="subtitle" class="main-hero-sub">{{ subtitle }}</div>
    </div>
    <i class="ti ti-robot main-hero-deco"></i>
  </div>
</template>

<style scoped>
.main-hero {
  position: relative;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  overflow: hidden;
  color: #fff;
  background: var(--gradient-brand);
}

/* 装饰性光斑 + 网格纹理，增强科技感 */
.main-hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(360px 140px at 82% 0%, rgba(255, 255, 255, 0.22), transparent 70%),
    radial-gradient(300px 160px at 12% 110%, rgba(255, 255, 255, 0.12), transparent 70%);
  pointer-events: none;
}

.main-hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.06) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: linear-gradient(90deg, transparent, #000 30%, #000);
  pointer-events: none;
}

.main-hero-text {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.main-hero-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: 0.5px;
  line-height: 1.3;
  text-shadow: 0 1px 4px rgba(31, 91, 196, 0.35);
}

.main-hero-title i {
  font-size: 18px;
}

.main-hero-sub {
  font-size: 12px;
  opacity: 0.85;
  letter-spacing: 1px;
}

.main-hero-deco {
  position: relative;
  z-index: 1;
  font-size: 44px;
  opacity: 0.28;
  flex-shrink: 0;
}

@media (max-width: 768px) {
  .main-hero {
    padding: 14px 16px;
  }
  .main-hero-title {
    font-size: 16px;
  }
  .main-hero-deco {
    display: none;
  }
}
</style>

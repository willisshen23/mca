<script setup>
import { computed } from 'vue';
import { useAnalysisStore } from '../../stores/analysisStore';

const store = useAnalysisStore();

const uploadText = computed(() => (
  store.state.uploadDone
    ? '2024线下活动数据.xlsx - 上传成功 (2.3 MB)'
    : '点击或拖拽文件至此处上传'
));

const uploadSub = computed(() => (
  store.state.uploadDone ? '点击重新选择' : '支持 .xlsx / .pdf / .docx，单文件 ≤ 20MB'
));

function updateStart(value) {
  store.setOfflineDates(value, store.state.offlineEnd);
}

function updateEnd(value) {
  store.setOfflineDates(store.state.offlineStart, value);
}
</script>

<template>
  <section class="sc">
    <div class="sh">
      <i class="ti ti-upload" style="color: var(--primary)"></i>
      <span class="stitle">离线文档上传</span>
    </div>
    <div class="itip">
      <i class="ti ti-info-circle"></i>
      线下活动数据源：上传本地分析文档（Excel/PDF/Word），并填写统计起止时间。
    </div>
    <div class="frow">
      <div class="fg">
        <label class="flabel">统计起始日期 <span class="req">*</span></label>
        <input class="fi" type="date" :value="store.state.offlineStart" @input="updateStart($event.target.value)" />
      </div>
      <div class="fg">
        <label class="flabel">统计截止日期 <span class="req">*</span></label>
        <input class="fi" type="date" :value="store.state.offlineEnd" @input="updateEnd($event.target.value)" />
      </div>
    </div>
    <button class="uz" :class="{ ok: store.state.uploadDone }" type="button" @click="store.toggleUpload">
      <i :class="store.state.uploadDone ? 'ti ti-circle-check' : 'ti ti-cloud-upload'"></i>
      <p>{{ uploadText }}</p>
      <small>{{ uploadSub }}</small>
    </button>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue';
import { uploadFile } from '../../api/files';
import { useAnalysisStore } from '../../stores/analysisStore';

const ACCEPTED_EXTENSIONS = ['.csv', '.xls', '.xlsx', '.xlsm', '.xltx', '.xltm'];

const store = useAnalysisStore();
const fileInputRef = ref(null);
const uploading = ref(false);
const uploadError = ref('');

const uploadText = computed(() => {
  if (uploading.value) return '正在上传...';
  if (store.state.offlineFile) return `${store.state.offlineFile.file_name} - 上传成功`;
  return '点击选择文件上传';
});

const uploadSub = computed(() => {
  if (uploadError.value) return uploadError.value;
  if (store.state.offlineFile) return '点击重新选择';
  return `支持 ${ACCEPTED_EXTENSIONS.join(' / ')} 文件`;
});

function updateStart(value) {
  store.setOfflineDates(value, store.state.offlineEnd);
}

function updateEnd(value) {
  store.setOfflineDates(store.state.offlineStart, value);
}

function triggerSelect() {
  if (uploading.value) return;
  uploadError.value = '';
  fileInputRef.value?.click();
}

async function handleFileChange(event) {
  const file = event.target.files?.[0];
  event.target.value = '';
  if (!file) return;
  const lowerName = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => lowerName.endsWith(ext))) {
    uploadError.value = `仅支持 ${ACCEPTED_EXTENSIONS.join('、')} 文件`;
    return;
  }
  uploading.value = true;
  uploadError.value = '';
  try {
    const result = await uploadFile(file);
    store.setOfflineFile({ file_name: result.file_name || file.name, file_path: result.file_path, size: file.size });
  } catch (e) {
    store.clearOfflineFile();
    uploadError.value = e.message || '文件上传失败';
  } finally {
    uploading.value = false;
  }
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
      线下活动数据源：上传本地分析文档（Excel/CSV 表格文件），并填写统计起止时间。
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
    <input
      ref="fileInputRef"
      type="file"
      style="display: none"
      :accept="ACCEPTED_EXTENSIONS.join(',')"
      @change="handleFileChange"
    />
    <button class="uz" :class="{ ok: store.state.offlineFile }" type="button" :disabled="uploading" @click="triggerSelect">
      <i :class="store.state.offlineFile ? 'ti ti-circle-check' : (uploading ? 'ti ti-loader-2' : 'ti ti-cloud-upload')"></i>
      <p>{{ uploadText }}</p>
      <small :style="uploadError ? 'color: var(--danger, #F53F3F)' : ''">{{ uploadSub }}</small>
    </button>
  </section>
</template>

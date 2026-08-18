<script setup>
import { nextTick } from 'vue';
import { useRouter } from 'vue-router';
import TopBar from '../components/layout/TopBar.vue';
import ChatPanel from '../components/common/ChatPanel.vue';
import ReportSummary from '../components/report/ReportSummary.vue';
import { useAnalysisStore } from '../stores/analysisStore';

const router = useRouter();
const store = useAnalysisStore();
const lockSummary = store.lockSummary;
const reportTitle = store.reportTitle;

function sendMessage(value) {
  store.addS3Message('usr', value);
  window.setTimeout(() => {
    store.addS3Message('ai', '正在基于报告数据分析，请稍候...');
  }, 200);
}

async function inlineTablerIconsCss() {
  try {
    const cssText = await fetch('/lib/tabler-icons.min.css').then((r) => r.text());
    const fontMap = {};
    const fontRegex = /url\(["']?\.\/fonts\/([^"')]+)["']?\)/g;
    let match;
    while ((match = fontRegex.exec(cssText)) !== null) {
      const rawPath = match[1];
      fontMap[rawPath] = rawPath.split('?')[0];
    }

    await Promise.all(
      Object.keys(fontMap).map(async (rawPath) => {
        const cleanPath = fontMap[rawPath];
        const res = await fetch(`/lib/fonts/${cleanPath}`);
        if (!res.ok) throw new Error(`加载字体失败: ${cleanPath}`);
        const blob = await res.blob();
        const dataUrl = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onloadend = () => resolve(reader.result);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
        fontMap[rawPath] = dataUrl;
      })
    );

    return cssText.replace(
      /url\(["']?\.\/fonts\/([^"')]+)["']?\)/g,
      (full, rawPath) => `url("${fontMap[rawPath]}")`
    );
  } catch (e) {
    console.warn('内联 Tabler Icons CSS 失败，导出 HTML 可能无法显示图标', e);
    return '';
  }
}

async function buildExportHtml() {
  const content = document.querySelector('.report-content')?.innerHTML || '';
  const currentTitle = store.reportTitle.value;
  const tablerCss = await inlineTablerIconsCss();
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${currentTitle}</title>
  ${tablerCss ? `<style>${tablerCss}</style>` : ''}
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; padding: 40px; background: #F7F8FA; color: #1D2129; }
    .sc,.rph,.rcard { background: #fff; border: 1px solid #E5E6EB; border-radius: 6px; padding: 16px; margin-bottom: 12px; }
    .rgrid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
    .rcardt,.stitle { font-size: 13px; font-weight: 600; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
    .krow { display: flex; gap: 10px; }
    .kpi { flex: 1; background: #F7F8FA; border-radius: 4px; padding: 10px; text-align: center; }
    .kpiv { font-size: 20px; font-weight: 600; color: #165DFF; }
    .kpil,.subtitle { font-size: 11px; color: #86909C; margin-top: 2px; }
    .barchart { display: flex; flex-direction: column; gap: 6px; }
    .brow { display: flex; align-items: center; gap: 8px; font-size: 11px; }
    .blabel { width: 72px; color: #4E5969; text-align: right; flex-shrink: 0; }
    .btrack { flex: 1; height: 14px; background: #F2F3F5; border-radius: 2px; overflow: hidden; }
    .bfill { height: 100%; background: #165DFF; }
    .bval { width: 32px; color: #4E5969; font-weight: 500; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .chip { background: #E8F0FF; color: #165DFF; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
    .ins { list-style: none; display: flex; flex-direction: column; gap: 5px; }
    .insi { font-size: 12px; padding: 6px 10px; background: #F7F8FA; border-radius: 4px; border-left: 3px solid #165DFF; line-height: 1.5; }
    .insi.w { border-left-color: #FF7D00; background: #FFF9F0; }
    .insi.g { border-left-color: #00B42A; background: #F3FFF5; }
    .aip { display: none; }
  </style>
</head>
<body>${content}</body>
</html>`;
}

async function downloadReport(extension, mimeType) {
  await nextTick();
  const currentTitle = store.reportTitle.value;
  const html = await buildExportHtml();
  const blob = new Blob([html], { type: mimeType });
  downloadBlob(blob, `${currentTitle}.${extension}`);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="page">
    <TopBar current-label="分析报告" :step="3" />
    <div class="content report-content">
      <section class="rph">
        <div style="font-size: 14px; font-weight: 600; display: flex; gap: 8px">
          <i class="ti ti-file-analytics" style="color: var(--primary)"></i>
          <span>{{ reportTitle }}</span>
        </div>
        <div style="display: flex; gap: 16px; margin-top: 8px; font-size: 12px; flex-wrap: wrap">
          <span><span style="color: var(--t3)">活动类型：</span>{{ lockSummary.typeName }}</span>
          <span><span style="color: var(--t3)">周期：</span>{{ lockSummary.period }}</span>
          <span><span style="color: var(--t3)">生成：</span>2024-04-01</span>
        </div>
        <div class="chips">
          <span v-for="skill in store.state.canvasComps" :key="skill.name" class="chip">{{ skill.name }}</span>
        </div>
      </section>

      <ReportSummary />

      <section class="sc">
        <div class="sh">
          <i class="ti ti-message-question" style="color: var(--primary)"></i>
          <span class="stitle">AI报告问答</span>
        </div>
        <ChatPanel :messages="store.state.s3Messages" title="AI报告问答" placeholder="提问..." @send="sendMessage" />
      </section>
    </div>
    <div class="fbar">
      <button class="btn" type="button" @click="router.push({ name: 'compose' })">
        <i class="ti ti-arrow-left"></i> 返回调整
      </button>
      <button class="btn pri" type="button" @click="downloadReport('html', 'text/html')">
        <i class="ti ti-code"></i> 导出HTML
      </button>
    </div>
  </div>
</template>

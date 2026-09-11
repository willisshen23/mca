// HTML 报告文档构建与导出（HTML 下载 / PNG 长图 / 新页签预览），
// 以及 iframe 高度自适应、PNG 快照桥接所需的脚本注入。
// 导出进度遮罩 exportOverlay 为模块级单例，同一页面任意报告卡片共享。

import { reactive } from 'vue';
import { API_BASE } from '@/api/base.js';
import { escapeHtmlText, safeDownloadName } from './chatUtils.js';

const IFRAME_RESIZE_SCRIPT = `(function() {
  function postHeight() {
    try {
      var h = document.documentElement.scrollHeight;
      if (window.parent && window.parent !== window) {
        window.parent.postMessage({ type: 'html-report-resize', height: h }, '*');
      }
    } catch (e) {}
  }
  function observe() {
    postHeight();
    try {
      var ro = window.ResizeObserver;
      if (ro) {
        var observer = new ro(postHeight);
        observer.observe(document.body);
      } else {
        window.addEventListener('resize', postHeight);
      }
    } catch (e) {}
  }
  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    observe();
  } else {
    window.addEventListener('load', observe);
  }
})();`;

const HTML_REPORT_MAX_HEIGHT = 1400;
const HTML_REPORT_MIN_HEIGHT = 360;
const PNG_EXPORT_TIMEOUT_MS = 90000;
const pendingPngExports = new Map();
let html2canvasLoader = null;

export const exportOverlay = reactive({ visible: false, label: '' });
let exportOperationId = 0;

export function beginReportExport(label) {
  exportOperationId += 1;
  exportOverlay.visible = true;
  exportOverlay.label = label;
  return exportOperationId;
}

export function finishReportExport(operationId) {
  if (operationId !== exportOperationId) return;
  exportOverlay.visible = false;
  exportOverlay.label = '';
}

function installPngSnapshotBridge() {
  let capturing = false;

  function postResult(requestId, payload) {
    window.parent.postMessage({
      type: 'html-report-png-snapshot',
      requestId,
      ...payload
    }, '*');
  }

  function waitForStableLayout() {
    return new Promise((resolve) => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          window.setTimeout(resolve, 700);
        });
      });
    });
  }

  function canvasToImage(canvas, clonedCanvas) {
    const image = document.createElement('img');
    const bounds = canvas.getBoundingClientRect();
    try {
      image.src = canvas.toDataURL('image/png');
    } catch (error) {
      throw new Error(`图表无法转换为图片：${error?.message || error}`);
    }
    image.alt = canvas.getAttribute('aria-label') || '报告图表';
    image.className = clonedCanvas.className || '';
    image.style.cssText = clonedCanvas.style.cssText || '';
    image.style.display = 'block';
    image.style.width = `${Math.max(Math.round(bounds.width), 1)}px`;
    image.style.height = `${Math.max(Math.round(bounds.height), 1)}px`;
    image.setAttribute('width', String(Math.max(Math.round(bounds.width), 1)));
    image.setAttribute('height', String(Math.max(Math.round(bounds.height), 1)));
    if (clonedCanvas.id) image.id = clonedCanvas.id;
    clonedCanvas.replaceWith(image);
  }

  function sanitizeSnapshot(root) {
    root.querySelectorAll(
      'script, noscript, iframe, object, embed, form, base, meta[http-equiv="refresh"]'
    ).forEach((node) => node.remove());
    root.querySelectorAll('*').forEach((element) => {
      for (const attribute of Array.from(element.attributes || [])) {
        const name = attribute.name.toLowerCase();
        if (name.startsWith('on') || name === 'srcdoc') {
          element.removeAttribute(attribute.name);
        }
      }
    });
    const style = document.createElement('style');
    style.textContent = '*,*::before,*::after{animation:none!important;transition:none!important;}';
    (root.querySelector('head') || root).appendChild(style);
  }

  async function createSnapshot(requestId) {
    if (capturing) {
      postResult(requestId, {
        success: false,
        error: 'PNG 报告正在生成，请稍候'
      });
      return;
    }
    capturing = true;
    try {
      if (document.fonts?.ready) {
        await document.fonts.ready;
      }
      await waitForStableLayout();
      const clone = document.documentElement.cloneNode(true);
      const sourceCanvases = Array.from(document.querySelectorAll('canvas'));
      const clonedCanvases = Array.from(clone.querySelectorAll('canvas'));
      sourceCanvases.forEach((canvas, index) => {
        const clonedCanvas = clonedCanvases[index];
        if (clonedCanvas) canvasToImage(canvas, clonedCanvas);
      });
      sanitizeSnapshot(clone);
      postResult(requestId, {
        success: true,
        html: `<!DOCTYPE html>${clone.outerHTML}`
      });
    } catch (error) {
      postResult(requestId, {
        success: false,
        error: error?.message || String(error)
      });
    } finally {
      capturing = false;
    }
  }

  window.addEventListener('message', (event) => {
    const data = event.data;
    if (
      event.source !== window.parent
      || !data
      || data.type !== 'html-report-png-request'
      || !data.requestId
    ) return;
    createSnapshot(data.requestId);
  });
}

function injectResizeScript(doc) {
  let head = doc.querySelector('head');
  if (!head) {
    head = doc.createElement('head');
    const htmlEl = doc.querySelector('html') || doc.documentElement;
    htmlEl.insertBefore(head, htmlEl.firstChild);
  }
  if (head.querySelector('script[data-iframe-resize]')) return;
  const script = doc.createElement('script');
  script.setAttribute('data-iframe-resize', 'true');
  script.textContent = IFRAME_RESIZE_SCRIPT;
  head.appendChild(script);
}

function injectPngSnapshotBridge(doc) {
  let head = doc.querySelector('head');
  if (!head) {
    head = doc.createElement('head');
    const htmlEl = doc.querySelector('html') || doc.documentElement;
    htmlEl.insertBefore(head, htmlEl.firstChild);
  }
  if (!head.querySelector('script[data-png-export-bridge]')) {
    const exportScript = doc.createElement('script');
    exportScript.setAttribute('data-png-export-bridge', 'true');
    exportScript.textContent = `(${installPngSnapshotBridge.toString()})();`;
    head.appendChild(exportScript);
  }
}

export function handleHtmlReportResize(event) {
  if (!event.data || event.data.type !== 'html-report-resize') return;
  const height = parseInt(event.data.height, 10);
  if (Number.isNaN(height) || height <= 0) return;
  const iframes = document.querySelectorAll('.html-report-preview');
  for (const iframe of iframes) {
    if (iframe.contentWindow === event.source) {
      const clamped = Math.min(Math.max(height, HTML_REPORT_MIN_HEIGHT), HTML_REPORT_MAX_HEIGHT);
      iframe.style.height = `${clamped}px`;
      break;
    }
  }
}

export function handlePngSnapshotResult(event) {
  const data = event.data;
  if (!data || data.type !== 'html-report-png-snapshot' || !data.requestId) return;
  const pending = pendingPngExports.get(data.requestId);
  if (!pending || event.source !== pending.iframe.contentWindow) return;

  window.clearTimeout(pending.timeoutId);
  pendingPngExports.delete(data.requestId);
  if (data.success && typeof data.html === 'string' && data.html) {
    pending.resolve(data.html);
  } else {
    pending.reject(new Error(data.error || '浏览器读取报告快照失败'));
  }
}

export function cancelPendingPngExports(reason = '页面已关闭，PNG 导出已取消') {
  for (const pending of pendingPngExports.values()) {
    window.clearTimeout(pending.timeoutId);
    pending.reject(new Error(reason));
  }
  pendingPngExports.clear();
}

export function buildHtmlDocument(message) {
  let html = (message.html || '').trim();
  if (!html) return '';
  // 兜底：去除 LLM 可能附带的前言文字，只保留从 HTML 标签开始的内容
  const htmlStartMatch = html.match(/<(html|!doctype|section|div|body|head|main|article)/i);
  if (htmlStartMatch && htmlStartMatch.index > 0) {
    html = html.slice(htmlStartMatch.index);
  }
  // 统一将 LLM 可能使用的任意 ECharts CDN 或路径替换为项目本地路径
  html = html.replace(
    /https?:\/\/[^"'\s]*echarts[^"'\s]*\.min\.js/gi,
    './lib/echarts.min.js'
  );

  // 使用 DOMParser 做结构化兜底：确保 echarts 库在 head 中同步加载，并修复裸 option 对象
  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const ECHARTS_SRC = './lib/echarts.min.js';

    // 规范化已有的 echarts 脚本引用。
    const scripts = Array.from(doc.querySelectorAll('script'));
    const echartsScripts = scripts.filter((s) => {
      const src = s.getAttribute('src') || '';
      return /echarts/i.test(src) && /\.min\.js$/i.test(src);
    });
    echartsScripts.forEach((s) => {
      s.setAttribute('src', ECHARTS_SRC);
      s.removeAttribute('async');
      s.removeAttribute('defer');
      if (s.getAttribute('type') === 'text/javascript') s.removeAttribute('type');
    });

    // 确保 head 中存在唯一一个 echarts 同步脚本。
    let head = doc.querySelector('head');
    if (!head) {
      head = doc.createElement('head');
      const htmlEl = doc.querySelector('html') || doc.documentElement;
      htmlEl.insertBefore(head, htmlEl.firstChild);
    }
    if (echartsScripts.length === 0) {
      const script = doc.createElement('script');
      script.setAttribute('src', ECHARTS_SRC);
      head.appendChild(script);
    } else {
      // 只保留第一个，移动到 head，其余删除。
      const first = echartsScripts[0];
      echartsScripts.slice(1).forEach((s) => s.remove());
      head.appendChild(first);
    }

    // 兜底修复裸 ECharts option 对象字面量：将 { ... } 包装成 IIFE。
    scripts.forEach((script) => {
      const content = script.textContent || '';
      const trimmed = content.trim();
      if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return;
      // 简单校验：是单一顶层对象字面量
      let depth = 0;
      let inString = false;
      let stringChar = null;
      let escaped = false;
      let isSingleObject = true;
      for (let i = 0; i < trimmed.length; i += 1) {
        const ch = trimmed[i];
        if (escaped) {
          escaped = false;
          continue;
        }
        if (ch === '\\') {
          escaped = true;
          continue;
        }
        if (inString) {
          if (ch === stringChar) inString = false;
          continue;
        }
        if (ch === '"' || ch === "'") {
          inString = true;
          stringChar = ch;
          continue;
        }
        if (ch === '{') depth += 1;
        else if (ch === '}') {
          depth -= 1;
          if (depth === 0 && i !== trimmed.length - 1) {
            isSingleObject = false;
            break;
          }
        }
      }
      if (!isSingleObject || depth !== 0 || inString) return;

      // 寻找最近的 chart 容器
      let chartId = null;
      let el = script.previousElementSibling;
      while (el && !chartId) {
        const id = el.getAttribute('id') || '';
        if (id.toLowerCase().startsWith('chart')) chartId = id;
        el = el.previousElementSibling;
      }
      if (!chartId) {
        const allCharts = Array.from(doc.querySelectorAll('[id^="chart-"], [id^="chart_"], [id^="chartA"], [id^="chartB"], [id^="chartC"], [id^="chartD"], [id^="chartE"], [id^="chartF"], [id^="chartG"], [id^="chartH"], [id^="chartI"], [id^="chartJ"], [id^="chartK"], [id^="chartL"], [id^="chartM"], [id^="chartN"], [id^="chartO"], [id^="chartP"], [id^="chartQ"], [id^="chartR"], [id^="chartS"], [id^="chartT"], [id^="chartU"], [id^="chartV"], [id^="chartW"], [id^="chartX"], [id^="chartY"], [id^="chartZ"], [id^="chart0"], [id^="chart1"], [id^="chart2"], [id^="chart3"], [id^="chart4"], [id^="chart5"], [id^="chart6"], [id^="chart7"], [id^="chart8"], [id^="chart9"]'));
        const scriptIndex = scripts.indexOf(script);
        const precedingCharts = allCharts.filter((c) => {
          const containers = Array.from(doc.querySelectorAll('div'));
          return containers.indexOf(c) < containers.indexOf(script);
        });
        chartId = precedingCharts[precedingCharts.length - 1]?.getAttribute('id');
      }
      if (!chartId) return;

      script.textContent = `(function() {\n  var chartDom = document.getElementById('${chartId}');\n  if (!chartDom) return;\n  var myChart = echarts.init(chartDom);\n  var option = ${trimmed};\n  myChart.setOption(option);\n  window.addEventListener('resize', function() { myChart.resize(); });\n})();`;
    });

    // 注入 iframe 高度自适应脚本，让预览 iframe 根据报告内容自动调整高度
    injectResizeScript(doc);
    // 沙箱 iframe 只回传无脚本静态快照，PNG 在父页面的同源环境生成。
    injectPngSnapshotBridge(doc);

    // 使用 outerHTML 做 HTML 序列化（而非 XMLSerializer），避免 <script> 中的 < > & 被转义为 XML 实体，
    // 否则浏览器会以 HTML 模式重新解析时不会解码 &lt; / &gt;，导致 JS 报 "lt is not defined" 等语法错误。
    const doctype = doc.doctype ? `<!DOCTYPE ${doc.doctype.name}>` : '';
    html = doctype + doc.documentElement.outerHTML;
  } catch (e) {
    console.warn('HTML 报告结构化兜底处理失败，使用原始 HTML', e);
  }

  const scriptOpen = '<' + 'script data-iframe-resize="true">';
  const scriptClose = '<' + '/script>';
  const pngBridgeScriptOpen = '<' + 'script data-png-export-bridge="true">';
  const escapedResizeScript = IFRAME_RESIZE_SCRIPT.replace(/<\/script/gi, '<\\/script');
  const escapedPngBridgeScript = `(${installPngSnapshotBridge.toString()})();`
    .replace(/<\/script/gi, '<\\/script');
  return html.toLowerCase().startsWith('<!doctype') || html.toLowerCase().startsWith('<html')
    ? html
    : `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${message.title || '活动分析报告'}</title>
  ${scriptOpen}${escapedResizeScript}${scriptClose}
  ${pngBridgeScriptOpen}${escapedPngBridgeScript}${scriptClose}
  <style>
    body { margin: 0; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color: #1f2937; line-height: 1.65; background: #fff; }
    h1, h2, h3 { color: #111827; line-height: 1.35; }
    h1 { font-size: 26px; margin: 0 0 16px; }
    h2 { font-size: 20px; margin: 24px 0 12px; }
    h3 { font-size: 16px; margin: 18px 0 10px; }
    p, li { font-size: 14px; color: #475569; }
    table { width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 13px; }
    th, td { border: 1px solid #e5e7eb; padding: 9px 10px; text-align: left; }
    th { background: #f8fafc; color: #334155; }
    pre { white-space: pre-wrap; word-break: break-word; background: #f8fafc; border-radius: 8px; padding: 12px; font-size: 12px; color: #334155; }
  </style>
</head>
<body>
${html}
</body>
</html>`;
}

export async function downloadHtmlReport(message) {
  const html = (message.html || '').trim();
  if (!html) return;
  const operationId = beginReportExport('正在导出 HTML 报告…');

  try {
    const response = await fetch(`${API_BASE}/reports/html`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        html,
        title: message.title || '活动分析报告'
      })
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `HTTP ${response.status}`);
    }
    const htmlBlob = await response.blob();
    const url = URL.createObjectURL(htmlBlob);
    const link = document.createElement('a');
    const date = new Date().toISOString().slice(0, 10);
    link.href = url;
    link.download = `活动分析报告-${date}.html`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error('下载HTML报告失败', e);
    alert('下载HTML报告失败：' + e.message);
  } finally {
    finishReportExport(operationId);
  }
}

function requestPngSnapshot(iframe) {
  return new Promise((resolve, reject) => {
    if (!iframe?.contentWindow) {
      reject(new Error('没有找到当前报告预览，请刷新页面后重试'));
      return;
    }
    const requestId = `png-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const timeoutId = window.setTimeout(() => {
      pendingPngExports.delete(requestId);
      reject(new Error('读取报告快照超时，请刷新页面后重试'));
    }, 15000);
    pendingPngExports.set(requestId, { iframe, timeoutId, resolve, reject });
    iframe.contentWindow.postMessage({
      type: 'html-report-png-request',
      requestId
    }, '*');
  });
}

function sanitizePngSnapshotHtml(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');
  doc.querySelectorAll(
    'script, noscript, iframe, object, embed, form, base, meta[http-equiv="refresh"]'
  ).forEach((node) => node.remove());
  doc.querySelectorAll('*').forEach((element) => {
    for (const attribute of Array.from(element.attributes || [])) {
      const name = attribute.name.toLowerCase();
      if (name.startsWith('on') || name === 'srcdoc') {
        element.removeAttribute(attribute.name);
      }
    }
  });
  return `<!DOCTYPE html>${doc.documentElement.outerHTML}`;
}

function waitForStaticFrame(iframe) {
  return new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(
      () => reject(new Error('静态报告渲染超时')),
      15000
    );
    iframe.addEventListener('load', () => {
      window.clearTimeout(timeoutId);
      resolve();
    }, { once: true });
    iframe.addEventListener('error', () => {
      window.clearTimeout(timeoutId);
      reject(new Error('静态报告加载失败'));
    }, { once: true });
  });
}

async function waitForSnapshotAssets(doc) {
  if (doc.fonts?.ready) {
    await doc.fonts.ready;
  }
  const images = Array.from(doc.images || []);
  await Promise.all(images.map((image) => {
    if (image.complete) return Promise.resolve();
    return new Promise((resolve) => {
      image.addEventListener('load', resolve, { once: true });
      image.addEventListener('error', resolve, { once: true });
    });
  }));
  await new Promise((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(resolve));
  });
}

function pngRenderScale(width, height) {
  const maxDimension = 16000;
  const maxPixels = 36000000;
  const scale = Math.min(
    2,
    maxDimension / width,
    maxDimension / height,
    Math.sqrt(maxPixels / (width * height))
  );
  if (!Number.isFinite(scale) || scale < 0.35) {
    throw new Error('报告内容过长，当前浏览器无法生成清晰的单张 PNG，请下载 HTML 报告');
  }
  return scale;
}

async function renderSnapshotToPng(snapshotHtml, viewportWidth) {
  if (!html2canvasLoader) {
    html2canvasLoader = import('html2canvas').then((module) => module.default);
  }
  const iframe = document.createElement('iframe');
  // 静态快照允许父页面同源读取，但禁止执行任何脚本。
  iframe.setAttribute('sandbox', 'allow-same-origin');
  iframe.setAttribute('aria-hidden', 'true');
  iframe.tabIndex = -1;
  Object.assign(iframe.style, {
    position: 'fixed',
    left: '-100000px',
    top: '0',
    width: `${Math.max(Math.round(viewportWidth || 0), 800)}px`,
    height: '900px',
    border: '0',
    pointerEvents: 'none'
  });

  const loaded = waitForStaticFrame(iframe);
  iframe.srcdoc = sanitizePngSnapshotHtml(snapshotHtml);
  document.body.appendChild(iframe);
  try {
    const [html2canvas] = await Promise.all([html2canvasLoader, loaded]);
    const doc = iframe.contentDocument;
    if (!doc?.body) throw new Error('无法读取静态报告内容');
    await waitForSnapshotAssets(doc);

    const body = doc.body;
    const root = doc.documentElement;
    const width = Math.max(
      body.scrollWidth,
      body.offsetWidth,
      root.scrollWidth,
      root.offsetWidth,
      1
    );
    const height = Math.max(
      body.scrollHeight,
      body.offsetHeight,
      root.scrollHeight,
      root.offsetHeight,
      1
    );
    const scale = pngRenderScale(width, height);
    const canvas = await Promise.race([
      html2canvas(body, {
        backgroundColor: '#ffffff',
        scale,
        useCORS: true,
        allowTaint: false,
        logging: false,
        scrollX: 0,
        scrollY: 0,
        width,
        height,
        windowWidth: width,
        windowHeight: height
      }),
      new Promise((_, reject) => {
        window.setTimeout(
          () => reject(new Error('PNG 生成超时，请稍后重试或下载 HTML 报告')),
          PNG_EXPORT_TIMEOUT_MS
        );
      })
    ]);
    return await new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => blob
          ? resolve(blob)
          : reject(new Error('浏览器生成 PNG 文件失败')),
        'image/png'
      );
    });
  } finally {
    iframe.remove();
  }
}

export async function downloadPngReport(message, event) {
  const operationId = beginReportExport('正在使用当前浏览器生成 PNG 报告…');
  try {
    const reportCard = event?.currentTarget?.closest('.html-report-card');
    const reportIframe = reportCard?.querySelector('.html-report-preview');
    const snapshotHtml = await requestPngSnapshot(reportIframe);
    const blob = await renderSnapshotToPng(
      snapshotHtml,
      reportIframe?.clientWidth
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const date = new Date().toISOString().slice(0, 10);
    link.href = url;
    link.download = `${safeDownloadName(message.title)}-${date}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error('下载PNG报告失败', error);
    alert(`下载PNG报告失败：${error.message || error}`);
  } finally {
    finishReportExport(operationId);
  }
}

export async function openHtmlReportInNewTab(message) {
  const reportWindow = window.open('', '_blank');
  if (!reportWindow) {
    alert('无法打开新页签，请允许浏览器弹出窗口后重试');
    return;
  }
  reportWindow.opener = null;
  reportWindow.document.open();
  reportWindow.document.write(`<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>${escapeHtmlText(message.title || '活动分析报告')}</title>
  <style>
    body { margin: 0; min-height: 100vh; display: grid; place-items: center; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color: #475569; background: #f8fafc; }
  </style>
</head>
<body>正在打开报告...</body>
</html>`);
  reportWindow.document.close();

  try {
    let documentHtml = buildHtmlDocument(message);
    if (!documentHtml) return;
    documentHtml = await inlineEchartsScript(documentHtml);
    reportWindow.document.open();
    reportWindow.document.write(documentHtml);
    reportWindow.document.close();
    reportWindow.focus();
  } catch (e) {
    console.error('新页签打开HTML报告失败', e);
    const errorMessage = escapeHtmlText(e.message || e);
    reportWindow.document.open();
    reportWindow.document.write(`<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>报告打开失败</title>
  <style>
    body { margin: 0; padding: 32px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color: #1f2937; background: #fff; }
    .error { max-width: 720px; margin: 0 auto; padding: 18px 20px; border: 1px solid #fecdd3; border-radius: 8px; background: #fff1f2; color: #b42318; }
  </style>
</head>
<body><div class="error">打开报告失败：${errorMessage}</div></body>
</html>`);
    reportWindow.document.close();
  }
}

async function inlineEchartsScript(html) {
  const response = await fetch('./lib/echarts.min.js');
  if (!response.ok) throw new Error('无法加载 echarts.min.js');
  const echartsScript = await response.text();

  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const scripts = Array.from(doc.querySelectorAll('script'));
    const echartsScripts = scripts.filter((script) => {
      const src = script.getAttribute('src') || '';
      return /echarts/i.test(src) && /\.js(\?.*)?$/i.test(src);
    });
    const inlineScript = doc.createElement('script');
    inlineScript.textContent = `\n${echartsScript}\n`;

    if (echartsScripts.length > 0) {
      echartsScripts[0].replaceWith(inlineScript);
      echartsScripts.slice(1).forEach((script) => script.remove());
    } else {
      const head = doc.querySelector('head') || doc.documentElement;
      head.appendChild(inlineScript);
    }

    const doctype = doc.doctype ? `<!DOCTYPE ${doc.doctype.name}>` : '<!doctype html>';
    return `${doctype}${doc.documentElement.outerHTML}`;
  } catch (e) {
    console.warn('内联 ECharts 失败，使用字符串替换兜底', e);
    const openingScript = '<' + 'script>';
    const closingScript = '<' + '/script>';
    const escapedScript = `${openingScript}\n${echartsScript.replace(new RegExp(closingScript, 'gi'), '<\\/script')}\n${closingScript}`;
    const echartsSrcPattern = new RegExp(
      '<' + 'script[^>]+src=["\'][^"\']*echarts[^"\']*["\'][^>]*>\\s*<' + '\\/script>',
      'i'
    );
    if (echartsSrcPattern.test(html)) {
      return html.replace(echartsSrcPattern, escapedScript);
    }
    const headClosePattern = new RegExp('<' + '\\/head\\s*>', 'i');
    if (headClosePattern.test(html)) {
      return html.replace(headClosePattern, `${escapedScript}</head>`);
    }
    return `${escapedScript}\n${html}`;
  }
}

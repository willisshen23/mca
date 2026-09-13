// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import {
  stripReportFooterNote, safeDownloadName, pngRenderScale,
  escapeHtmlText, buildHtmlDocument, getAppBaseUrl, echartsScriptUrl
} from './htmlReport.js';

describe('htmlReport', () => {
  it('stripReportFooterNote 去除数据来源尾注', () => {
    const html = '<div><p>正文</p><p>数据来源：行内系统</p></div>';
    expect(stripReportFooterNote(html)).not.toContain('数据来源');
    expect(stripReportFooterNote(html)).toContain('正文');
  });

  it('safeDownloadName 清理非法字符并截断', () => {
    expect(safeDownloadName('a/b:c*d?"<>|')).toBe('a_b_c_d_');
    expect(safeDownloadName('')).toBe('活动分析报告');
    expect(safeDownloadName('x'.repeat(200)).length).toBeLessThanOrEqual(80);
  });

  it('pngRenderScale 正常尺寸返回 ≤2 的缩放', () => {
    expect(pngRenderScale(800, 1200)).toBe(2);
  });

  it('pngRenderScale 超大尺寸抛错', () => {
    expect(() => pngRenderScale(50000, 50000)).toThrow();
  });

  it('escapeHtmlText 转义特殊字符', () => {
    expect(escapeHtmlText('<b>"x"</b>')).toBe('&lt;b&gt;&quot;x&quot;&lt;/b&gt;');
  });

  it('buildHtmlDocument 注入 echarts 同步脚本与 resize 桥', () => {
    const out = buildHtmlDocument({ title: '测试', html: '<html><head></head><body><div id="chart-1"></div><script>{ "series": [] }</script></body></html>' });
    // echarts 引用指向解析后的部署路径：srcdoc iframe / 新页签的 baseURL 是宿主页面 URL，
    // 在 /main/analysis/report 等嵌套路由下相对路径会解析成 /main/analysis/lib/... 导致 404
    expect(out).toContain('/lib/echarts.min.js');
    expect(out).toContain('data-iframe-resize');
    // 图表尺寸监督脚本：纠正 iframe 内以错误容器尺寸初始化的 ECharts 图表
    expect(out).toContain('data-chart-resize');
    expect(out).toContain('getInstanceByDom');
    // CDN 形式的 echarts 引用统一替换为本地路径
    const cdn = buildHtmlDocument({ title: 't', html: '<html><head><script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script></head><body></body></html>' });
    expect(cdn).not.toContain('cdn.jsdelivr.net');
  });

  it('getAppBaseUrl 无构建产物脚本时回退为根路径', () => {
    expect(getAppBaseUrl()).toBe('/');
    expect(echartsScriptUrl()).toBe('/lib/echarts.min.js');
  });

  it('getAppBaseUrl 从 assets 脚本反推子路径部署前缀', () => {
    const script = document.createElement('script');
    script.src = 'https://example.com:9002/activity/assets/index-abc123.js';
    document.head.appendChild(script);
    try {
      expect(getAppBaseUrl()).toBe('https://example.com:9002/activity/');
      expect(echartsScriptUrl()).toBe('https://example.com:9002/activity/lib/echarts.min.js');
    } finally {
      script.remove();
    }
  });

  it('getAppBaseUrl 根路径部署时反推为站点根', () => {
    const script = document.createElement('script');
    script.src = 'https://example.com:8080/assets/index-abc123.js';
    document.head.appendChild(script);
    try {
      expect(getAppBaseUrl()).toBe('https://example.com:8080/');
    } finally {
      script.remove();
    }
  });
});

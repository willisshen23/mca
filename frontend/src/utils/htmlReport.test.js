// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import {
  stripReportFooterNote, safeDownloadName, pngRenderScale,
  escapeHtmlText, buildHtmlDocument
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
    // 必须用站点根绝对路径：srcdoc iframe / 新页签的 baseURL 是宿主页面 URL，
    // 在 /main/analysis/report 等嵌套路由下相对路径会解析成 /main/analysis/lib/... 导致 404
    expect(out).toContain('/lib/echarts.min.js');
    expect(out).toContain('data-iframe-resize');
    // CDN 形式的 echarts 引用统一替换为本地路径
    const cdn = buildHtmlDocument({ title: 't', html: '<html><head><script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script></head><body></body></html>' });
    expect(cdn).not.toContain('cdn.jsdelivr.net');
  });
});

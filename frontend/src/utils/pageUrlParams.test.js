// @vitest-environment jsdom
import { describe, expect, it, beforeEach } from 'vitest';
import { getPageUrlParams } from './pageUrlParams.js';

function setUrl(url) {
  window.history.replaceState(null, '', url);
}

describe('getPageUrlParams', () => {
  beforeEach(() => {
    setUrl('/');
  });

  it('读取 search 上的入口挂参（/?srcSysNo=x#/route 形式）', () => {
    setUrl('/?srcSysNo=ABC&userId=u1#/main/analysis/report');
    const params = getPageUrlParams();
    expect(params.get('srcSysNo')).toBe('ABC');
    expect(params.get('userId')).toBe('u1');
  });

  it('读取 hash 路由内部 query（/#/route?srcSysNo=x 形式）', () => {
    setUrl('/#/main/analysis/report?srcSysNo=HASH');
    expect(getPageUrlParams().get('srcSysNo')).toBe('HASH');
  });

  it('同名参数 hash query 优先于 search', () => {
    setUrl('/?srcSysNo=OUTER#/main?srcSysNo=INNER');
    expect(getPageUrlParams().get('srcSysNo')).toBe('INNER');
  });

  it('无参数时返回空', () => {
    setUrl('/#/main');
    expect(getPageUrlParams().get('srcSysNo')).toBeNull();
  });
});

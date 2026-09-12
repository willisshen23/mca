// 统一读取页面级 URL 挂参：同时解析 location.search（/?a=1#/route 形式）
// 与 hash 路由内部 query（/#/route?a=1 形式），同名参数 hash query 优先。
// Hash 路由下外部系统入口参数通常挂在 search 上，而 router.push({ query }) 的参数
// 落在 hash query 里，两处都要覆盖，避免换路由模式后丢参数。
export function getPageUrlParams() {
  const merged = new URLSearchParams(window.location.search);
  const hash = window.location.hash || '';
  const queryIndex = hash.indexOf('?');
  if (queryIndex >= 0) {
    const hashParams = new URLSearchParams(hash.slice(queryIndex + 1));
    hashParams.forEach((value, key) => merged.set(key, value));
  }
  return merged;
}

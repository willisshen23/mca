import { safeSetItem } from '@/utils/safeStorage.js';
import { getPageUrlParams } from '@/utils/pageUrlParams.js';

export function useChatUrlParams() {
  const params = getPageUrlParams();
  const userId = (params.get('userId') || '').trim();
  const userName = (params.get('userName') || '').trim();
  const orgNo = (params.get('orgNo') || '').trim();
  const srcSysNo = (params.get('srcSysNo') || '').trim();

  // localStorage 可能被会话缓存占满（QuotaExceededError），
  // safeSetItem 会淘汰最旧会话缓存后重试；仍失败不阻断页面挂载——
  // 挂参仍通过返回值生效。
  const persisted = [
    ['user_id', userId],
    ['org_no', orgNo],
    ['user_name', userName],
    ['src_sys_no', srcSysNo]
  ].every(([key, value]) => !value || safeSetItem(key, value));
  if (!persisted) {
    console.warn('URL 参数写入 localStorage 失败（存储已满且无缓存可清理）');
  }
  const effectiveUserName = userName || (localStorage.getItem('user_name') || '').trim();
  const effectiveOrgNo = orgNo || (localStorage.getItem('org_no') || '').trim();
  const effectiveSrcSysNo = srcSysNo || (localStorage.getItem('src_sys_no') || '').trim();

  return {
    userId,
    userName: effectiveUserName,
    orgNo: effectiveOrgNo,
    srcSysNo: effectiveSrcSysNo,
    channel: userId || effectiveOrgNo ? 'AILMIS' : ''
  };
}

export function useChatUrlParams() {
  const params = new URLSearchParams(window.location.search);
  const userId = (params.get('userId') || '').trim();
  const userName = (params.get('userName') || '').trim();
  const orgNo = (params.get('orgNo') || '').trim();
  const srcSysNo = (params.get('srcSysNo') || '').trim();

  // localStorage 可能被会话缓存占满（QuotaExceededError），
  // 持久化失败不应阻断页面挂载——挂参仍通过返回值生效。
  try {
    if (userId) {
      localStorage.setItem('user_id', userId);
    }
    if (orgNo) {
      localStorage.setItem('org_no', orgNo);
    }
    if (userName) {
      localStorage.setItem('user_name', userName);
    }
    if (srcSysNo) {
      localStorage.setItem('src_sys_no', srcSysNo);
    }
  } catch (e) {
    console.warn('URL 参数写入 localStorage 失败（可能存储已满）', e);
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

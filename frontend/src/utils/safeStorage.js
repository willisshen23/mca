// 带配额自愈的 localStorage 写入。
// 会话消息缓存（chat_dynamic_messages:*）只增不减，长期累积会写满
// 同源 localStorage 配额，之后所有 setItem（包括 user_id 这类小 key）
// 都会抛 QuotaExceededError。safeSetItem 在配额满时按插入顺序
// 淘汰最旧的本应用会话/续传缓存后重试，仍失败则返回 false 而不抛错。
export const CHAT_STORAGE_PREFIX = 'chat_dynamic_messages:';
export const RUN_SEQUENCE_PREFIX = 'agent_run_sequence:';

const EVICTABLE_PREFIXES = [CHAT_STORAGE_PREFIX, RUN_SEQUENCE_PREFIX];

function isQuotaExceeded(error) {
  return error?.name === 'QuotaExceededError'
    || error?.code === 22 // 旧浏览器 DOMException
    || error?.code === 1014; // Firefox NS_ERROR_DOM_QUOTA_REACHED
}

function evictableKeys(storage, excludeKey) {
  const keys = [];
  for (let i = 0; i < storage.length; i += 1) {
    const key = storage.key(i);
    if (key && key !== excludeKey && EVICTABLE_PREFIXES.some((prefix) => key.startsWith(prefix))) {
      keys.push(key);
    }
  }
  return keys;
}

export function safeSetItem(key, value, { storage = localStorage } = {}) {
  try {
    storage.setItem(key, value);
    return true;
  } catch (error) {
    if (!isQuotaExceeded(error)) return false;
    // 配额满：逐个淘汰最旧的可淘汰缓存后重试
    for (const oldKey of evictableKeys(storage, key)) {
      try {
        storage.removeItem(oldKey);
        storage.setItem(key, value);
        return true;
      } catch (retryError) {
        if (!isQuotaExceeded(retryError)) return false;
      }
    }
    return false;
  }
}

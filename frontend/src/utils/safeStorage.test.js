// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest';
import { safeSetItem, CHAT_STORAGE_PREFIX, RUN_SEQUENCE_PREFIX } from './safeStorage.js';

function quotaError() {
  return new DOMException('quota exceeded', 'QuotaExceededError');
}

// 模拟容量有限的 localStorage：capacity 字节写满后抛 QuotaExceededError
function makeFullStorage(initial = {}, capacity = 100) {
  const data = new Map(Object.entries(initial));
  const usage = () => [...data.entries()].reduce((sum, [k, v]) => sum + k.length + v.length, 0);
  return {
    get length() { return data.size; },
    key: (i) => [...data.keys()][i] ?? null,
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    removeItem: (k) => data.delete(k),
    setItem: (k, v) => {
      const next = new Map(data);
      next.set(k, String(v));
      const nextUsage = [...next.entries()].reduce((sum, [kk, vv]) => sum + kk.length + vv.length, 0);
      if (nextUsage > capacity) throw quotaError();
      data.clear();
      next.forEach((val, key) => data.set(key, val));
    },
    _usage: usage,
    _keys: () => [...data.keys()]
  };
}

describe('safeStorage.safeSetItem', () => {
  beforeEach(() => localStorage.clear());

  it('容量充足时直接写入', () => {
    expect(safeSetItem('user_id', 'u1')).toBe(true);
    expect(localStorage.getItem('user_id')).toBe('u1');
  });

  it('配额满时淘汰最旧会话缓存后重试成功', () => {
    const storage = makeFullStorage({
      [`${CHAT_STORAGE_PREFIX}old-1`]: 'x'.repeat(40),
      [`${CHAT_STORAGE_PREFIX}old-2`]: 'y'.repeat(40)
    }, 95);
    expect(safeSetItem('user_id', 'new-user', { storage })).toBe(true);
    expect(storage.getItem('user_id')).toBe('new-user');
    // 最旧的会话缓存被淘汰
    expect(storage.getItem(`${CHAT_STORAGE_PREFIX}old-1`)).toBe(null);
  });

  it('不淘汰非本应用会话缓存的 key', () => {
    const storage = makeFullStorage({
      user_name: 'someone',
      [`${CHAT_STORAGE_PREFIX}old-1`]: 'x'.repeat(40)
    }, 95);
    expect(safeSetItem('user_id', 'new-user', { storage })).toBe(true);
    expect(storage.getItem('user_name')).toBe('someone');
  });

  it('不淘汰正在写入的会话 key 本身', () => {
    const key = `${CHAT_STORAGE_PREFIX}current`;
    const storage = makeFullStorage({ [key]: 'x'.repeat(30) }, 40);
    // 写入更大的值会超容量，且唯一可淘汰的就是自己 → 放弃
    expect(safeSetItem(key, 'z'.repeat(50), { storage })).toBe(false);
    expect(storage.getItem(key)).toBe('x'.repeat(30));
  });

  it('无可淘汰缓存仍失败时返回 false 而不抛错', () => {
    const storage = makeFullStorage({ user_name: 'x'.repeat(90) }, 95);
    expect(safeSetItem('user_id', 'new-user-id', { storage })).toBe(false);
  });

  it('可淘汰运行序号缓存', () => {
    const storage = makeFullStorage({
      [`${RUN_SEQUENCE_PREFIX}old-1`]: 'x'.repeat(40)
    }, 70);
    expect(safeSetItem('user_id', 'new-user', { storage })).toBe(true);
    expect(storage.getItem(`${RUN_SEQUENCE_PREFIX}old-1`)).toBe(null);
  });

  it('非配额类异常不重试直接失败', () => {
    const storage = {
      ...makeFullStorage({}),
      setItem: () => { throw new TypeError('boom'); }
    };
    expect(safeSetItem('k', 'v', { storage })).toBe(false);
  });
});

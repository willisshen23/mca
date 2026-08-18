import { API_BASE } from './base.js';

// crypto.randomUUID 仅在安全上下文(HTTPS/localhost)可用,
// HTTP 部署或旧浏览器下会缺失,这里提供降级实现。
function generateUUID() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80; // variant
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0'));
    return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10, 16).join('')}`;
  }
  // 最后兜底:Math.random(非加密,仅保证唯一性)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function getUserId() {
  let uid = localStorage.getItem('user_id');
  if (!uid) {
    uid = generateUUID();
    try {
      localStorage.setItem('user_id', uid);
    } catch (e) {
      // 存储已满时降级为会话内临时 id，不阻断请求
      console.warn('user_id 写入 localStorage 失败（可能存储已满）', e);
    }
  }
  return uid;
}

async function request(path, options = {}) {
  const userId = getUserId();
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': userId,
      ...(options.headers || {})
    },
    ...options
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败：${response.status}`);
  }
  return response.json();
}

export async function fetchConversations() {
  const userId = getUserId();
  const data = await request(`/conversations?user_id=${userId}`);
  return data.conversations || [];
}

export async function createConversationAPI(title) {
  const userId = getUserId();
  const data = await request('/conversations', {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, title })
  });
  return data;
}

export async function deleteConversationAPI(threadId) {
  const userId = getUserId();
  const data = await request(`/conversations/${threadId}?user_id=${userId}`, {
    method: 'DELETE'
  });
  return data;
}

export async function renameConversationAPI(threadId, title) {
  const userId = getUserId();
  const data = await request(`/conversations/${threadId}`, {
    method: 'PATCH',
    body: JSON.stringify({ user_id: userId, title })
  });
  return data;
}

export async function fetchConversationMessages(threadId) {
  const userId = getUserId();
  const data = await request(`/conversations/${threadId}?user_id=${userId}`);
  return {
    messages: data.messages || [],
    agentVersion: data.agent_version || '',
    htmlReport: data.html_report || '',
    reportContext: data.report_context || null,
    reportHistory: data.report_history || null,
    reportHistories: data.report_histories || [],
    reportPlacements: data.report_placements || [],
    runtimeTrace: data.runtime_trace || null
  };
}

export { getUserId };

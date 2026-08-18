import { API_BASE } from './base.js';

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
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

export async function fetchConversationLogs(params = {}) {
  const query = new URLSearchParams();
  if (params.keyword) query.set('keyword', params.keyword);
  if (params.userId) query.set('user_id', params.userId);
  if (params.threadId) query.set('thread_id', params.threadId);
  if (params.status) query.set('status', params.status);
  query.set('limit', String(params.limit || 20));
  query.set('offset', String(params.offset || 0));
  return request(`/conversation-logs?${query.toString()}`);
}

export async function fetchThreadTurns(threadId) {
  return request(`/conversation-logs/thread/${encodeURIComponent(threadId)}`);
}

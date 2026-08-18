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

export async function fetchSystemPrompts(params = {}) {
  const query = new URLSearchParams();
  if (params.status && params.status !== 'all') query.set('status', params.status);
  if (params.keyword) query.set('keyword', params.keyword);
  const suffix = query.toString() ? `?${query}` : '';
  const data = await request(`/system-prompts${suffix}`);
  return data.prompts || [];
}

export async function createSystemPrompt(payload) {
  const data = await request('/system-prompts', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  return data.prompt;
}

export async function updateSystemPrompt(promptId, payload) {
  const data = await request(`/system-prompts/${promptId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
  return data.prompt;
}

export async function publishSystemPrompt(promptId, payload = {}) {
  const data = await request(`/system-prompts/${promptId}/publish`, {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  return data.prompt;
}

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

export async function fetchQuickPrompts() {
  const data = await request('/quick-prompts');
  return data.prompts || [];
}

export async function fetchAdminQuickPrompts() {
  const data = await request('/quick-prompts/admin');
  return data.prompts || [];
}

export async function saveAdminQuickPrompts(prompts) {
  const data = await request('/quick-prompts/admin', {
    method: 'PUT',
    body: JSON.stringify({ prompts })
  });
  return data.prompts || [];
}

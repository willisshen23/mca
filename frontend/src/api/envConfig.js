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

export async function fetchEnvConfig() {
  return request('/env-config');
}

export async function updateEnvConfig(content) {
  return request('/env-config', {
    method: 'PATCH',
    body: JSON.stringify({ content })
  });
}

export async function restartBackend() {
  return request('/env-config/restart', {
    method: 'POST'
  });
}

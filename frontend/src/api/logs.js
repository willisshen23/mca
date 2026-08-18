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

export async function fetchLogFiles() {
  return request('/logs/files');
}

export async function fetchLogContent(params = {}) {
  const query = new URLSearchParams();
  if (params.filename) query.set('filename', params.filename);
  if (params.lines) query.set('lines', String(params.lines));
  if (params.tail !== undefined) query.set('tail', String(params.tail));
  const response = await fetch(`${API_BASE}/logs/content?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  return response.text();
}

export async function downloadLogFile(filename) {
  const response = await fetch(`${API_BASE}/logs/download/${encodeURIComponent(filename)}`);
  if (!response.ok) {
    throw new Error(`下载失败：${response.status}`);
  }
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

export async function tailLog(params = {}) {
  const query = new URLSearchParams();
  if (params.lines) query.set('lines', String(params.lines));
  if (params.filename) query.set('filename', params.filename);
  const response = await fetch(`${API_BASE}/logs/tail?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  return response.text();
}
import { API_BASE } from './base.js';
import { getUserId } from './conversations.js';

function generateSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getSessionId() {
  const key = 'usage_session_id';
  let sessionId = sessionStorage.getItem(key);
  if (!sessionId) {
    sessionId = generateSessionId();
    sessionStorage.setItem(key, sessionId);
  }
  return sessionId;
}

export function getOrgNo() {
  const params = new URLSearchParams(window.location.search);
  const orgNo = (params.get('orgNo') || params.get('org_no') || '').trim();
  if (orgNo) {
    try {
      localStorage.setItem('org_no', orgNo);
    } catch (e) {
      console.warn('org_no 写入 localStorage 失败（可能存储已满）', e);
    }
    return orgNo;
  }
  return (localStorage.getItem('org_no') || '').trim();
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getUserId(),
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `请求失败：${response.status}`);
  }
  return response.json();
}

export function fetchUsageSummary(days = 30) {
  return request(`/usage-dashboard/summary?days=${days}`);
}

export async function downloadUsageDetails(days = 30) {
  const response = await fetch(`${API_BASE}/usage-dashboard/export?days=${days}`, {
    headers: { 'X-User-Id': getUserId() }
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `导出失败：${response.status}`);
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const fileName = encodedName
    ? decodeURIComponent(encodedName)
    : `usage-details-${new Date().toISOString().slice(0, 10)}.xlsx`;
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return fileName;
}

export function recordUsageEvent(eventType, details = {}) {
  return request('/usage-dashboard/events', {
    method: 'POST',
    body: JSON.stringify({
      event_type: eventType,
      org_no: getOrgNo() || null,
      session_id: getSessionId(),
      path: window.location.pathname,
      referrer: document.referrer || null,
      ...details
    })
  });
}

import { API_BASE } from './base.js';
import { getUserId } from './conversations.js';

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

export async function fetchHistorySessions(params = {}) {
  const query = new URLSearchParams();
  if (params.keyword) query.set('keyword', params.keyword);
  if (params.feedback) query.set('feedback', params.feedback);
  if (params.dateFrom) query.set('date_from', params.dateFrom);
  if (params.dateTo) query.set('date_to', params.dateTo);
  query.set('limit', String(params.limit || 20));
  query.set('offset', String(params.offset || 0));
  return request(`/agent-run-history/sessions?${query.toString()}`);
}

export async function fetchHistorySessionDetail(threadId) {
  return request(`/agent-run-history/sessions/${encodeURIComponent(threadId)}`);
}

export function exportHistorySessionsUrl(params = {}) {
  const query = new URLSearchParams();
  if (params.keyword) query.set('keyword', params.keyword);
  if (params.feedback) query.set('feedback', params.feedback);
  if (params.dateFrom) query.set('date_from', params.dateFrom);
  if (params.dateTo) query.set('date_to', params.dateTo);
  const suffix = query.toString();
  return `${API_BASE}/agent-run-history/sessions/export${suffix ? `?${suffix}` : ''}`;
}

export async function fetchRunHistories(params = {}) {
  const query = new URLSearchParams();
  if (params.keyword) query.set('keyword', params.keyword);
  if (params.requestId) query.set('request_id', params.requestId);
  if (params.status) query.set('status', params.status);
  if (params.feedback) query.set('feedback', params.feedback);
  query.set('limit', String(params.limit || 100));
  query.set('offset', String(params.offset || 0));
  return request(`/agent-run-history?${query.toString()}`);
}

export function exportHistoriesUrl(params = {}) {
  const query = new URLSearchParams();
  if (params.keyword) query.set('keyword', params.keyword);
  if (params.requestId) query.set('request_id', params.requestId);
  if (params.status) query.set('status', params.status);
  if (params.feedback) query.set('feedback', params.feedback);
  const suffix = query.toString();
  return `${API_BASE}/agent-run-history/export${suffix ? `?${suffix}` : ''}`;
}

export async function fetchRunHistoryDetail(id) {
  return request(`/agent-run-history/${id}`);
}

export async function submitReportFeedback(requestId, feedback, threadId = '', { versionNo, comment } = {}) {
  const cleanRequestId = String(requestId || '').trim();
  const cleanThreadId = String(threadId || '').trim();
  const path = cleanRequestId
    ? `/agent-run-history/${encodeURIComponent(cleanRequestId)}/feedback`
    : `/agent-run-history/thread/${encodeURIComponent(cleanThreadId)}/feedback`;
  const body = {
    feedback,
    user_id: getUserId()
  };
  if (versionNo !== undefined && versionNo !== null) {
    body.version_no = versionNo;
  }
  if (comment !== undefined && comment !== null && String(comment).trim() !== '') {
    body.comment = String(comment).trim();
  }
  return request(path, {
    method: 'POST',
    body: JSON.stringify(body)
  });
}

export function reportDownloadUrl(id, format = 'html', versionNo = null) {
  const targetFormat = format || 'html';
  const query = new URLSearchParams();
  if (targetFormat !== 'html') query.set('format', targetFormat);
  if (versionNo !== undefined && versionNo !== null) {
    query.set('version_no', String(versionNo));
  }
  const suffix = query.toString();
  return `${API_BASE}/agent-run-history/${id}/report${suffix ? `?${suffix}` : ''}`;
}

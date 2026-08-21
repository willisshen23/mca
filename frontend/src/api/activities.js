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

export async function fetchOnlineActivities(params = {}) {
  const query = new URLSearchParams();
  if (params.keyword) query.set('keyword', params.keyword);
  if (params.activityType) query.set('activity_type', params.activityType);
  if (params.startDate) query.set('start_date', params.startDate);
  if (params.endDate) query.set('end_date', params.endDate);
  if (params.page) query.set('page', params.page);
  if (params.pageSize) query.set('page_size', params.pageSize);
  const suffix = query.toString() ? `?${query}` : '';
  const data = await request(`/online-activities${suffix}`);
  return {
    activities: data.activities || [],
    page: data.page || 1,
    pageSize: data.page_size || params.pageSize || 20,
    hasMore: Boolean(data.has_more)
  };
}

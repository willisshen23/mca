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

export async function fetchSkills(params = {}) {
  const query = new URLSearchParams();
  if (params.categoryId) query.set('category_id', params.categoryId);
  if (params.keyword) query.set('keyword', params.keyword);
  const suffix = query.toString() ? `?${query}` : '';
  const data = await request(`/skills${suffix}`);
  return data.skills || [];
}

export async function fetchSkillCategories() {
  const data = await request('/skill-categories');
  return data.categories || [];
}

export async function createSkillCategory(payload) {
  const data = await request('/skill-categories', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  return data.category;
}

export async function createSkill(payload) {
  const data = await request('/skills', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  return data.skill;
}

export async function updateSkill(skillId, payload) {
  const data = await request(`/skills/${skillId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
  return data.skill;
}

export async function deleteSkillAPI(skillId) {
  const data = await request(`/skills/${skillId}`, {
    method: 'DELETE'
  });
  return data;
}

export async function deleteSkillCategory(categoryId) {
  const data = await request(`/skill-categories/${categoryId}`, {
    method: 'DELETE'
  });
  return data;
}

export async function updateSkillCategory(skillId, categoryId) {
  const data = await request(`/skills/${skillId}/category?category_id=${categoryId}`, {
    method: 'PATCH'
  });
  return data.skill;
}

export async function fetchActivityTemplates(params = {}) {
  const query = new URLSearchParams();
  if (params.type) query.set('type', params.type);
  if (params.keyword) query.set('keyword', params.keyword);
  const suffix = query.toString() ? `?${query}` : '';
  const data = await request(`/activity-templates${suffix}`);
  return data.templates || [];
}

export async function createActivityTemplate(payload) {
  const data = await request('/activity-templates', {
    method: 'POST',
    body: JSON.stringify(payload)
  });
  return data.template;
}

export async function updateActivityTemplate(templateId, payload) {
  const data = await request(`/activity-templates/${templateId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload)
  });
  return data.template;
}

export async function deleteActivityTemplate(templateId) {
  const data = await request(`/activity-templates/${templateId}`, {
    method: 'DELETE'
  });
  return data;
}

export async function applyActivityTemplate(templateId) {
  const data = await request(`/activity-templates/${templateId}/apply`, {
    method: 'POST'
  });
  return data.template;
}

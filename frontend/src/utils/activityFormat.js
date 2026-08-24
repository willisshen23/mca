// 活动对象字段兼容与选择相关的纯函数，从 UiChatView 抽取。
import { activityStatusTone, displayActivityStatus, displayActivityType } from './activityDictionaries.js';

export function compactActivity(activity = {}) {
  return {
    row_number: Number(activity?.row_number) || null,
    activity_id: activityId(activity),
    name: activityName(activity),
    channel: activity?.channel || activity?.['渠道'] || '',
    activity_type: activity?.activity_type || activity?.actTypeCd || activity?.['活动类型'] || '',
    status: activity?.status || activity?.actStatusCd || activity?.['活动状态'] || '',
    start_date: activity?.start_date || activity?.actStartDt || activity?.['活动开始日期'] || '',
    end_date: activity?.end_date || activity?.actEndDt || activity?.['活动结束日期'] || '',
    goal: activity?.goal || activity?.target || activity?.['活动运营目标'] || '',
    content: activitySummary(activity)
  };
}

export function compactTemplate(template = {}) {
  return {
    template_id: template.template_id || template.id || template.code || '',
    template_name: template.template_name || template.name || '',
    similarity_score: template.similarity_score,
    similarity_rank: template.similarity_rank,
    ...(template.reasoning ? { reasoning: template.reasoning } : {}),
    ...(template.match_strategy ? { match_strategy: template.match_strategy } : {}),
    ...(template.top_n ? { top_n: template.top_n } : {}),
    skill_sequence: Array.isArray(template.skill_sequence) ? template.skill_sequence : [],
    dependent_components: Array.isArray(template.dependent_components)
      ? template.dependent_components.map((item) => ({
          position: item.position,
          component_id: item.component_id || item.id || '',
          name: item.display_name || item.name || item.skill_name || '',
          skill_name: item.skill_name || item.name || '',
          ...(item.skill_description ? { skill_description: item.skill_description } : {}),
          ...(item.skill_category ? { skill_category: item.skill_category } : {}),
          // 展示模板预览可能较长，持久化时截断，避免 localStorage 超限
          ...(item.skill_template_preview
            ? { skill_template_preview: String(item.skill_template_preview).slice(0, 2000) }
            : {}),
          ...(Array.isArray(item.metrics) && item.metrics.length ? { metrics: item.metrics } : {})
        }))
      : []
  };
}

export function compactTracePayload(payload = {}) {
  return {
    ...(payload.marketing_intent ? { marketing_intent: payload.marketing_intent } : {}),
    ...(payload.activity_query_params ? { activity_query_params: payload.activity_query_params } : {}),
    ...(Array.isArray(payload.activity_list) ? { activity_list: payload.activity_list.map(compactActivity) } : {}),
    ...(payload.selected_activity_ids ? { selected_activity_ids: payload.selected_activity_ids } : {}),
    ...(payload.activity_route_result ? { activity_route_result: payload.activity_route_result } : {}),
    ...(payload.workflow_mode ? { workflow_mode: payload.workflow_mode } : {}),
    ...(payload.outbound_activity_data_found !== undefined ? { outbound_activity_data_found: payload.outbound_activity_data_found } : {}),
    ...(payload.template_match_result ? { template_match_result: compactTemplate(payload.template_match_result) } : {}),
    ...(Array.isArray(payload.matched_data_templates) ? { matched_data_templates: payload.matched_data_templates.map(compactTemplate) } : {}),
    ...(payload.activity_template_match_result ? { activity_template_match_result: compactTemplate(payload.activity_template_match_result) } : {}),
    // 分析能力清单只保留名称，足够思维面板展示，避免持久化体积膨胀
    ...(Array.isArray(payload.template_list)
      ? { template_list: payload.template_list.map((item) => ({ template_name: item?.template_name || item?.name || '' })) }
      : {}),
    ...(payload.component_value_cleanup_result ? { component_value_cleanup_result: payload.component_value_cleanup_result } : {})
  };
}

export function activityName(activity) {
  return activity?.name || activity?.activity_name || activity?.act_name || activity?.actName || activity?.['活动名称'] || activity?.activity_id || activity?.act_no || activity?.actNo || activity?.['活动编号'] || '未命名活动';
}

export function activityId(activity) {
  return activity?.activity_id || activity?.act_no || activity?.actNo || activity?.actNO || activity?.act_no_id || activity?.['活动编号'] || activity?.['活动ID'] || activity?.['活动id'] || '';
}

export function activityRowNumber(activity, fallbackIndex = 0) {
  const rowNumber = Number(activity?.row_number);
  return Number.isInteger(rowNumber) && rowNumber > 0 ? rowNumber : fallbackIndex + 1;
}

export function activityPeriod(activity) {
  const start = activity?.start_date || activity?.actStartDt || activity?.['活动开始日期'] || '';
  const end = activity?.end_date || activity?.actEndDt || activity?.['活动结束日期'] || '';
  if (start && end) return `${start} 至 ${end}`;
  return start || end || '';
}

export function activityTags(activity) {
  const rawType = activity?.activity_type || activity?.actTypeCd || activity?.['活动类型'] || '';
  const rawStatus = activity?.status || activity?.actStatusCd || activity?.['活动状态'] || '';
  const typeLabel = displayActivityType(rawType, rawStatus);
  const statusLabel = displayActivityStatus(rawStatus);
  return [
    typeLabel ? { key: `type:${typeLabel}`, label: typeLabel, kind: 'type', tone: 'type' } : null,
    statusLabel ? { key: `status:${statusLabel}`, label: statusLabel, kind: 'status', tone: activityStatusTone(rawStatus) } : null
  ].filter(Boolean);
}

export function activitySummary(activity) {
  return activity?.content || activity?.actDesc || activity?.['活动内容'] || activity?.target_segment || activity?.['目标客群'] || '';
}

export function visibleActivities(activities) {
  return Array.isArray(activities) ? activities.slice(0, 6) : [];
}

export function toggleActivitySelectionPure(message, activity) {
  const id = activityId(activity);
  if (!id) return;
  const selected = new Set(message.selectedIds || []);
  if (selected.has(id)) {
    selected.delete(id);
  } else {
    selected.add(id);
  }
  message.selectedIds = Array.from(selected);
}

export function selectionActivities(message) {
  return Array.isArray(message?.selectableActivities)
    ? message.selectableActivities
    : (Array.isArray(message?.activities) ? message.activities : []);
}

// 统计回复正文里「可选择的活动表格」的数据行数，判定条件与 markdown.js 渲染器一致：
// 首列表头为「序号」（行才可点选），且表头含活动标识列（活动名称/活动编号/活动ID）。
// 决策类提问是纯文字、没有表格，即使业务状态里带着 activity_list，
// 用户也无从点选，此时不应出现「已选 N 行 / 全选 / 全不选」等任何选择 UI。
export function selectableActivityRowCount(message) {
  const text = String(message?.text || '');
  if (!text.includes('|')) return 0;
  const lines = text.split('\n');
  let count = 0;
  for (let i = 0; i < lines.length - 1; i += 1) {
    const trimmed = lines[i].trim();
    if (!trimmed.includes('|')) continue;
    // 分隔行判定与 markdown.js isTableSeparator 保持一致
    const separator = lines[i + 1];
    if (!(/^\|?[\s:|-]+\|[\s:|-]*$/.test(separator.trim()) && separator.includes('-'))) continue;
    const headers = trimmed.replace(/^\|/, '').replace(/\|$/, '')
      .split('|')
      .map((cell) => cell.replace(/<[^>]+>|[*_`]/g, '').trim());
    if (headers[0] !== '序号') continue;
    if (!headers.some((header) => ['活动名称', '活动编号', '活动ID'].includes(header))) continue;
    let j = i + 2;
    while (j < lines.length && lines[j].trim().includes('|') && lines[j].trim()) {
      const firstCell = lines[j].trim().replace(/^\|/, '').split('|')[0];
      if (Number.isInteger(Number.parseInt(firstCell, 10))) count += 1;
      j += 1;
    }
    i = j - 1;
  }
  return count;
}

export function allActivitySelectionChecked(message) {
  const ids = selectionActivities(message).map((activity) => activityId(activity)).filter(Boolean);
  const selected = new Set(message?.selectedIds || []);
  return ids.length > 0 && ids.every((id) => selected.has(id));
}

export function selectedActivityRowNumbers(message) {
  const selected = new Set(message?.selectedIds || []);
  return selectionActivities(message)
    .map((activity, index) => ({
      id: activityId(activity),
      rowNumber: activityRowNumber(activity, index)
    }))
    .filter((item) => selected.has(item.id))
    .map((item) => item.rowNumber);
}

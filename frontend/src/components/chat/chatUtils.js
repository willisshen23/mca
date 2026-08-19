// 对话引擎纯函数工具：trace 步骤命名/排序/合并、活动信息提取、持久化压缩等。
// 全部不依赖 Vue 响应式状态，可在 UiChatView / ReportView 等页面间复用。

import {
  activityStatusTone,
  displayActivityStatus,
  displayActivityType
} from '@/utils/activityDictionaries.js';

export const SYSTEM_BUSY_MESSAGE = '系统繁忙，请稍后再试';

const TRANSPORT_ERROR_MARKERS = [
  'failed to fetch',
  'network error',
  'networkerror',
  'load failed',
  'fetch failed',
  'timed out',
  'timeout',
  'terminated',
  'connection reset',
  'connection closed',
  '请求超时',
  '网络异常',
  '网络错误',
  '连接中断',
  '连接已关闭'
];

export function isTransportError(error) {
  const name = String(error?.name || '').toLowerCase();
  const message = String(error?.message || error || '').toLowerCase();
  return name === 'aborterror'
    || name === 'timeouterror'
    || TRANSPORT_ERROR_MARKERS.some((marker) => message.includes(marker));
}

export function requestErrorMessage(error, prefix = '请求失败：') {
  if (isTransportError(error)) return SYSTEM_BUSY_MESSAGE;
  return `${prefix}${error?.message || error || '未知错误'}`;
}

/* ---------- 活动信息提取 ---------- */

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

/* ---------- trace 步骤 ---------- */

export function stepKey(step) {
  return step?.node || step?.step || step?.displayName || step?.message || '';
}

const TRACE_STEP_DISPLAY_NAMES = {
  intent_recognition: '意图识别',
  marketing_data_fetch: '活动获取',
  selected_activity_router: '活动查询与选择',
  outbound_activity_data_fetch: '外呼活动数据查询',
  file_upload: '文件解析',
  activity_file_parse: '上传活动数据解析',
  template_list_fetch: '分析能力准备',
  template_matching: '分析组件匹配',
  component_value_fetch: '组件数值获取',
  uploaded_component_value_extract: '上传活动指标整理',
  component_value_cleanup: '组件值清理',
  branch_drilldown: '支行机构对比',
  activity_template_matching: '活动报告模板匹配',
  marketing_report_synthesis: '报告生成',
  data_analysis: '数据分析',
  report_generation: '报告生成',
  format_conversion: '格式转换',
  report_validation: '报告校验',
  data_pipeline_merged: '数据获取、处理与分析',
  uploaded_file_parse_merged: '活动数据文件上传与解析',
  uploaded_data_processing_merged: '数据处理与分析'
};

export function traceDisplayName(stepOrKey, fallback = '') {
  const key = typeof stepOrKey === 'string' ? stepOrKey : stepKey(stepOrKey);
  return TRACE_STEP_DISPLAY_NAMES[key] || fallback || key || '处理中';
}

const TRACE_STEP_ORDER = [
  'intent_recognition',
  'marketing_data_fetch',
  'selected_activity_router',
  'outbound_activity_data_fetch',
  'file_upload',
  'activity_file_parse',
  'template_list_fetch',
  'template_matching',
  'component_value_fetch',
  'uploaded_component_value_extract',
  'component_value_cleanup',
  'branch_drilldown',
  'activity_template_matching',
  'marketing_report_synthesis',
  'data_analysis',
  'report_generation',
  'format_conversion',
  'report_validation'
];

const HIDDEN_TRACE_STEPS = new Set(['report_html_guard', 'branch_drilldown']);

export function traceStepOrder(step) {
  const index = TRACE_STEP_ORDER.indexOf(stepKey(step));
  return index >= 0 ? index : TRACE_STEP_ORDER.length + 1;
}

// 需要合并成“数据获取、处理与分析”一个展示步骤的节点（单/多活动通用）
const DATA_PIPELINE_MERGE_GROUP = [
  'template_list_fetch',
  'template_matching',
  'component_value_fetch',
  'component_value_cleanup'
];

const UPLOADED_FILE_PARSE_MERGE_GROUP = [
  'file_upload',
  'activity_file_parse'
];

const UPLOADED_DATA_PROCESSING_MERGE_GROUP = [
  'uploaded_component_value_extract',
  'component_value_cleanup'
];

function isSingleActivityTrace(steps) {
  return steps.some((step) => (
    step?.payload?.workflow_mode === 'single_activity_outbound_first'
    || stepKey(step) === 'outbound_activity_data_fetch'
  ));
}

// 单活动场景额外把“外呼活动数据查询”并入合并步骤
function dataPipelineMergeGroup(steps) {
  return isSingleActivityTrace(steps)
    ? ['outbound_activity_data_fetch', ...DATA_PIPELINE_MERGE_GROUP]
    : DATA_PIPELINE_MERGE_GROUP;
}

function buildMergedDataPipelineStep(group) {
  return buildMergedTraceStep(
    group,
    'data_pipeline_merged',
    '数据获取、处理与分析',
    '正在获取活动数据并实时匹配分析组件、计算指标...'
  );
}

function buildMergedTraceStep(group, node, displayName, runningMessage) {
  const terminal = ['done', 'failed', 'skipped'];
  const statuses = group.map((step) => step.status || 'pending');
  let status;
  if (statuses.includes('running')) status = 'running';
  else if (statuses.every((item) => item === 'pending')) status = 'pending';
  else if (statuses.every((item) => terminal.includes(item))) status = statuses.includes('failed') ? 'failed' : 'done';
  else status = 'running';
  const message = status === 'running'
    ? runningMessage
    : stepStatusText(status);
  const timestamp = group.reduce((min, step) => Math.min(min, step.timestamp || min), group[0]?.timestamp || Date.now());
  const payload = group.reduce((merged, step) => ({
    ...merged,
    ...(step.payload || {})
  }), {});
  return {
    node,
    displayName,
    message,
    status,
    payload,
    timestamp
  };
}

// 将数据获取/组件匹配等步骤折叠为一个展示步骤（仅影响展示，不改动 trace 状态数据）
function mergeDataPipelineSteps(sortedSteps, mergeGroup) {
  const group = sortedSteps.filter((step) => mergeGroup.includes(stepKey(step)));
  if (group.length === 0) return sortedSteps;
  const result = [];
  let inserted = false;
  sortedSteps.forEach((step) => {
    if (mergeGroup.includes(stepKey(step))) {
      if (!inserted) {
        result.push(buildMergedDataPipelineStep(group));
        inserted = true;
      }
      return;
    }
    result.push(step);
  });
  return result;
}

function isUploadedActivityTrace(steps) {
  return steps.some((step) => (
    stepKey(step) === 'uploaded_component_value_extract'
    || stepKey(step) === 'activity_file_parse'
    || step?.payload?.uploaded_activity_dataset
  ));
}

function mergeUploadedActivityTraceSteps(sortedSteps) {
  const groups = [
    {
      keys: UPLOADED_FILE_PARSE_MERGE_GROUP,
      node: 'uploaded_file_parse_merged',
      displayName: '活动数据文件上传与解析',
      runningMessage: '正在上传并解析活动数据文件...'
    },
    {
      keys: UPLOADED_DATA_PROCESSING_MERGE_GROUP,
      node: 'uploaded_data_processing_merged',
      displayName: '数据处理与分析',
      runningMessage: '正在处理上传数据并整理分析指标...'
    }
  ];
  let result = [...sortedSteps];
  groups.forEach((config) => {
    const group = result.filter((step) => config.keys.includes(stepKey(step)));
    if (group.length === 0) return;
    let inserted = false;
    const mergedStep = buildMergedTraceStep(
      group,
      config.node,
      config.displayName,
      config.runningMessage
    );
    result = result.flatMap((step) => {
      if (!config.keys.includes(stepKey(step))) return [step];
      if (inserted) return [];
      inserted = true;
      return [mergedStep];
    });
  });
  return result;
}

export function visibleTraceSteps(message) {
  const steps = Array.isArray(message?.steps) ? message.steps : [];
  const uploadedTrace = isUploadedActivityTrace(steps);
  const hasBusinessSteps = steps.some((step) => TRACE_STEP_ORDER.includes(stepKey(step)));
  const visible = steps.filter((step) => {
    const key = stepKey(step);
    return (
      !HIDDEN_TRACE_STEPS.has(key)
      && (!hasBusinessSteps || !['supervisor', 'finalize'].includes(key))
      && !step.skipReason
    );
  });
  // 已启动/已完成的步骤按真实时间排序，避免工具调用步骤被甩到底部造成“后面已完成、前面还在执行”的错觉；
  // pending 的计划步骤仍按业务顺序排在末尾，作为待执行预告
  const sorted = [...visible].sort((a, b) => {
    const aPending = isPendingStep(a);
    const bPending = isPendingStep(b);
    if (aPending || bPending) {
      if (aPending && bPending) return traceStepOrder(a) - traceStepOrder(b);
      return aPending ? 1 : -1;
    }
    return (a.timestamp || 0) - (b.timestamp || 0);
  });
  const displaySteps = uploadedTrace
    ? mergeUploadedActivityTraceSteps(sorted)
    : mergeDataPipelineSteps(sorted, dataPipelineMergeGroup(steps));
  return displaySteps.map((step) => ({
    ...step,
    displayName: uploadedTrace && stepKey(step) === 'selected_activity_router'
      ? '上传数据识别'
      : traceDisplayName(step, step.displayName)
  }));
}

export function isTraceNode(step, node) {
  return stepKey(step) === node;
}

export function stepStatusText(status) {
  if (status === 'done') return '已完成';
  if (status === 'running') return '执行中';
  if (status === 'failed') return '执行失败';
  if (status === 'skipped') return '已跳过';
  return '待执行';
}

export function isPendingStep(step) {
  return step?.status === 'pending';
}

export function upsertTraceStep(trace, nextStep) {
  const key = stepKey(nextStep);
  if (!key) return;
  if (HIDDEN_TRACE_STEPS.has(key)) return;
  nextStep.displayName = traceDisplayName(key, nextStep.displayName);
  const existing = trace.steps.find((item) => stepKey(item) === key);
  if (existing) {
    // node_update 带来的进度文案在步骤到达终态时应替换为状态文本，避免残留“正在 xxxx”
    const isTerminal = ['done', 'failed', 'skipped'].includes(nextStep.status);
    const message = isTerminal ? stepStatusText(nextStep.status) : nextStep.message;
    Object.assign(existing, {
      ...nextStep,
      ...(message !== undefined ? { message } : {}),
      payload: {
        ...(existing.payload || {}),
        ...(nextStep.payload || {})
      },
      timestamp: nextStep.timestamp || existing.timestamp
    });
  } else {
    trace.steps.push(nextStep);
  }
}

export function tracePayloadForStep(step, payload = {}) {
  if (step === 'intent_recognition') {
    return payload.marketing_intent ? { marketing_intent: payload.marketing_intent } : {};
  }
  if (step === 'marketing_data_fetch') {
    return {
      ...(payload.activity_query_params ? { activity_query_params: payload.activity_query_params } : {}),
      ...(payload.activity_list ? { activity_list: payload.activity_list } : {})
    };
  }
  if (step === 'activity_file_parse') {
    return {
      ...(payload.uploaded_activity_dataset ? { uploaded_activity_dataset: payload.uploaded_activity_dataset } : {}),
      ...(payload.activity_list ? { activity_list: payload.activity_list } : {})
    };
  }
  if (step === 'selected_activity_router') {
    return {
      ...(payload.activity_route_result ? { activity_route_result: payload.activity_route_result } : {}),
      ...(payload.workflow_mode ? { workflow_mode: payload.workflow_mode } : {}),
      ...(payload.activity_list ? { activity_list: payload.activity_list } : {})
    };
  }
  if (step === 'outbound_activity_data_fetch') {
    return {
      ...(payload.workflow_mode ? { workflow_mode: payload.workflow_mode } : {}),
      ...(payload.outbound_activity_data_found !== undefined ? { outbound_activity_data_found: payload.outbound_activity_data_found } : {}),
      ...(payload.outbound_activity_data ? { outbound_activity_data: payload.outbound_activity_data } : {})
    };
  }
  if (step === 'template_list_fetch') {
    return payload.template_list ? { template_list: payload.template_list } : {};
  }
  if (step === 'template_matching') {
    return {
      ...(payload.template_match_result ? { template_match_result: payload.template_match_result } : {}),
      ...(payload.matched_data_templates ? { matched_data_templates: payload.matched_data_templates } : {})
    };
  }
  if (step === 'component_value_fetch') {
    return {
      ...(payload.component_value_params ? { component_value_params: payload.component_value_params } : {}),
      ...(payload.component_values ? { component_values: payload.component_values } : {})
    };
  }
  if (step === 'uploaded_component_value_extract') {
    return {
      ...(payload.component_value_params ? { component_value_params: payload.component_value_params } : {}),
      ...(payload.component_values ? { component_values: payload.component_values } : {})
    };
  }
  if (step === 'component_value_cleanup') {
    return {
      ...(payload.component_value_cleanup_result ? { component_value_cleanup_result: payload.component_value_cleanup_result } : {}),
      ...(payload.component_values ? { component_values: payload.component_values } : {})
    };
  }
  if (step === 'activity_template_matching') {
    return {
      ...(payload.activity_template_list ? { activity_template_list: payload.activity_template_list } : {}),
      ...(payload.activity_template_match_result ? { activity_template_match_result: payload.activity_template_match_result } : {})
    };
  }
  if (step === 'marketing_report_synthesis' || step === 'report_generation') {
    return payload.html_report ? { html_report: payload.html_report } : {};
  }
  return {};
}

export function syncTracePlan(trace, plan = [], payload = {}) {
  if (!Array.isArray(plan) || plan.length === 0) return;
  plan.forEach((planStep) => {
    if (!planStep?.step) return;
    if (HIDDEN_TRACE_STEPS.has(planStep.step)) return;
    const stepPayload = planStep.status === 'pending' ? {} : tracePayloadForStep(planStep.step, payload);
    const existing = trace.steps.find((item) => stepKey(item) === planStep.step);
    if (existing) {
      existing.status = planStep.status || existing.status || 'pending';
      existing.displayName = traceDisplayName(planStep.step, existing.displayName || planStep.desc || planStep.step);
      existing.payload = planStep.status === 'pending'
        ? {}
        : {
            ...(existing.payload || {}),
            ...stepPayload
          };
      existing.skipReason = planStep.skip_reason || '';
      // 步骤到达终态（已完成/失败/跳过）时，把运行中的进度文案替换为状态文本，避免残留“正在 xxxx”
      const isTerminal = ['done', 'failed', 'skipped'].includes(planStep.status);
      if (isTerminal) {
        existing.message = stepStatusText(planStep.status);
        existing.fromPlan = true;
      } else if (!existing.message || existing.fromPlan) {
        existing.message = stepStatusText(planStep.status);
        existing.fromPlan = true;
      }
      return;
    }
    trace.steps.push({
      node: planStep.step,
      displayName: traceDisplayName(planStep.step, planStep.desc || planStep.step),
      message: stepStatusText(planStep.status),
      status: planStep.status || 'pending',
      payload: stepPayload,
      skipReason: planStep.skip_reason || '',
      timestamp: Date.now(),
      fromPlan: true
    });
  });
  if (payload.activity_list) {
    const activityStep = trace.steps.find((item) => stepKey(item) === 'marketing_data_fetch');
    if (activityStep) {
      activityStep.payload = {
        ...(activityStep.payload || {}),
        activity_list: payload.activity_list,
        ...(payload.activity_query_params ? { activity_query_params: payload.activity_query_params } : {})
      };
    }
  }
}

export function finishThinkingTrace(trace, payload = {}) {
  if (!trace) return;
  const isPaused = Boolean(
    payload.awaiting_activity_selection || payload.awaiting_approval
  );
  trace.status = isPaused ? 'paused' : 'done';
  trace.payload = payload;
  trace.durationMs = Math.max(1, Date.now() - (trace.startedAt || Date.now()));
  trace.expanded = isPaused;
  // 将未被实际执行的 pending 步骤标记为 skipped：paused 表示后续续跑会执行，done 表示不会执行
  if (Array.isArray(trace.steps)) {
    trace.steps.forEach((step) => {
      if (step.status === 'pending') {
        step.status = 'skipped';
        step.skipReason = step.skipReason || (isPaused ? '后续步骤将在选择活动后继续执行' : '未在当前流程中执行');
        step.message = stepStatusText('skipped');
      }
    });
  }
}

export function traceProgressText(message) {
  const steps = visibleTraceSteps(message);
  const total = steps.length;
  if (!total) return '0/0';
  const progressed = steps.filter((step) => ['running', 'done', 'failed', 'skipped'].includes(step.status)).length;
  const done = steps.filter((step) => ['done', 'failed', 'skipped'].includes(step.status)).length;
  return `${message.status === 'running' ? Math.max(progressed, 1) : Math.max(done, progressed)}/${total}`;
}

export function shouldDisplayThinkingTrace(message) {
  const steps = visibleTraceSteps(message);
  if (!steps.length) return false;
  if (message?.status === 'running' || message?.status === 'paused') return true;
  return steps.some((step) => ['done', 'failed', 'running'].includes(step.status));
}

export function thinkingTitleText(message) {
  if (message.status === 'running') return '正在思考';
  if (message.status === 'paused') return '等待选择';
  return '已思考';
}

export function activityTraceLabel(step) {
  return isTraceNode(step, 'selected_activity_router') ? '已选择活动' : '匹配活动';
}

export function activityRouteSummary(step) {
  if (step?.status === 'pending') return '等待执行';
  const result = step?.payload?.activity_route_result;
  if (result?.summary) return result.summary;
  if (step?.payload?.workflow_mode === 'single_activity_outbound_first') {
    return '单个活动，优先查询外呼业务数据；如未命中，再实时匹配分析组件计算指标。';
  }
  if (step?.payload?.workflow_mode === 'template_component_report') {
    return '多个活动，结合活动数据实时匹配分析组件并计算指标。';
  }
  return '';
}

// 数据模板匹配结果：优先 template_match_result（含 matched_data_templates），
// 否则取 matched_data_templates 首位作为主匹配。
export function templateMatchResult(step) {
  if (isPendingStep(step)) return null;
  const payload = step?.payload || {};
  if (payload.template_match_result) return payload.template_match_result;
  const list = payload.matched_data_templates;
  return Array.isArray(list) && list.length > 0 ? list[0] : null;
}

export function templateMatchCandidates(step) {
  if (isPendingStep(step)) return [];
  const payload = step?.payload || {};
  const list = payload.matched_data_templates || payload.template_match_result?.matched_data_templates || [];
  return Array.isArray(list) ? list : [];
}

export function activityTemplateMatchResult(step) {
  if (isPendingStep(step)) return null;
  return step?.payload?.activity_template_match_result || null;
}

export function templateListNames(step) {
  const list = step?.payload?.template_list;
  if (!Array.isArray(list)) return [];
  return list.map((item) => item?.template_name || item?.name || '').filter(Boolean);
}

// 展示条件：非等待态直接看 payload（template_list_fetch/template_matching 会被合并进
// data_pipeline_merged 步骤，payload 随之合并，按节点名判断会漏掉合并步骤）；
// 等待态只在原子步骤上显示“等待执行”，避免合并步骤出现占位详情框。
export function showTemplateMatchDetail(step) {
  if (isPendingStep(step)) return stepKey(step) === 'template_matching';
  return Boolean(templateMatchResult(step) || (step?.payload && step.payload.template_match_result));
}

export function showTemplateListDetail(step) {
  if (isPendingStep(step)) return stepKey(step) === 'template_list_fetch';
  return Array.isArray(step?.payload?.template_list);
}

/* ---------- 持久化压缩 ---------- */

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

/* ---------- 审批展示 ---------- */

export function formatApprovalArgs(args = {}) {
  const entries = Object.entries(args).filter(([, value]) => value !== undefined && value !== '');
  if (entries.length === 0) return '无参数';
  return entries.map(([key, value]) => {
    let display = value;
    if (Array.isArray(value)) display = value.join('、');
    else if (typeof value === 'object') display = JSON.stringify(value);
    return `${key}：${display}`;
  }).join('；');
}

export function formatApprovalDescription(message = {}) {
  if (message.tool === 'modify_report') {
    const args = message.args || {};
    const parts = [];
    const contentChanges = args.content_changes || [];
    if (contentChanges.length) {
      parts.push(`内容修改：${contentChanges.join('；')}`);
    }
    const chartReplacements = args.chart_replacements || [];
    if (chartReplacements.length) {
      const items = chartReplacements.map((item) => {
        const cid = item?.chart_id || '未指定';
        const toType = item?.to_chart_type || '未指定';
        return `将 ${cid} 替换为 ${toType}`;
      });
      parts.push(`图表替换：${items.join('；')}`);
    }
    const styleChanges = args.style_changes || [];
    if (styleChanges.length) {
      parts.push(`样式调整：${styleChanges.join('；')}`);
    }
    if (args.free_instruction) {
      parts.push(`其他要求：${args.free_instruction}`);
    }
    return parts.length ? parts.join('\n') : '无具体修改说明';
  }
  return formatApprovalArgs(message.args);
}

/* ---------- 其它 ---------- */

export function escapeHtmlText(value) {
  return String(value || '').replace(/[<>&"]/g, (ch) => ({
    '<': '&lt;',
    '>': '&gt;',
    '&': '&amp;',
    '"': '&quot;'
  }[ch]));
}

export function safeDownloadName(value, fallback = '活动分析报告') {
  return String(value || fallback)
    .replace(/[\\/:*?"<>|\r\n]+/g, '_')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80) || fallback;
}

// 剥离历史报告中"数据来源：…"一类的页脚尾注（新生成的报告已由后端清理，
// 这里兜底处理库存量报告）。
export function stripReportFooterNote(html) {
  if (!html) return html;
  return html
    .replace(/\s*<(p|div|footer|section|span)\b[^>]*>\s*(?:报告生成时间[:：][^<\n\r]*)?数据来源[:：][^<\n\r]*\s*<\/\1>\s*/gi, '')
    .replace(/^[ \t]*(?:报告生成时间[:：][^<\n\r]*)?数据来源[:：][^<\n\r]*[ \t]*\r?\n?/gim, '')
    .replace(/\s*<(p|div|footer|section|span)\b[^>]*>\s*报告基于[^<\n\r]*?生成[^<\n\r]*\s*<\/\1>\s*/gi, '')
    .replace(/^[ \t]*报告基于[^<\n\r]*?生成[^<\n\r]*[ \t]*\r?\n?/gim, '');
}

// 报告卡片的原始位置：产生它的用户轮次之后、下一轮用户消息之前。
export function findReportInsertIndex(messages, userOrdinal) {
  let seen = -1;
  for (let i = 0; i < messages.length; i++) {
    if (messages[i].role !== 'user') continue;
    seen++;
    if (seen === userOrdinal) {
      for (let j = i + 1; j < messages.length; j++) {
        if (messages[j].role === 'user') return j;
      }
      return messages.length;
    }
  }
  return messages.length;
}

export function restoredReportPayload(detail = {}) {
  return {
    ...(detail.reportHistory || {}),
    report_context: detail.reportContext || null
  };
}

export function parseUserSelectionContent(content) {
  const source = String(content || '');
  const match = source.match(/^已选择第\s*([\d\s、,，]+)\s*行(?:\r?\n)?/);
  if (!match) return { text: source, selectedRows: [] };
  const selectedRows = match[1]
    .split(/[、,，\s]+/)
    .map((value) => Number(value))
    .filter((value) => Number.isInteger(value) && value > 0);
  return {
    text: source.slice(match[0].length).trim(),
    selectedRows
  };
}

export function formatMeta(updatedAt) {
  if (!updatedAt) return '刚刚';
  const normalized = /([zZ]|[+-]\d{2}:?\d{2})$/.test(updatedAt)
    ? updatedAt
    : `${updatedAt}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return '刚刚';
  const now = new Date();
  const diff = Math.max(0, now - date);
  if (diff < 60000) return '刚刚';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
  return `${Math.floor(diff / 86400000)}天前`;
}

export function calculateGroup(updatedAt) {
  if (!updatedAt) return 'today';
  const normalized = /([zZ]|[+-]\d{2}:?\d{2})$/.test(updatedAt)
    ? updatedAt
    : `${updatedAt}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return 'today';
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const diffDays = Math.floor((now - date) / 86400000);
  if (isToday) return 'today';
  if (diffDays <= 7) return 'recent';
  return 'older';
}

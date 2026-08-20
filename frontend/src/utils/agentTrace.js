// 思维链（execution_trace）展示相关的纯函数，从 UiChatView 抽取，供对话页与报告页共用。

export function stepKey(step) {
  return step?.node || step?.step || step?.displayName || step?.message || '';
}

export const TRACE_STEP_DISPLAY_NAMES = {
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

export const TRACE_STEP_ORDER = [
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

export const HIDDEN_TRACE_STEPS = new Set(['report_html_guard', 'branch_drilldown']);

export function traceStepOrder(step) {
  const index = TRACE_STEP_ORDER.indexOf(stepKey(step));
  return index >= 0 ? index : TRACE_STEP_ORDER.length + 1;
}

// 需要合并成“数据获取、处理与分析”一个展示步骤的节点（单/多活动通用）
export const DATA_PIPELINE_MERGE_GROUP = [
  'template_list_fetch',
  'template_matching',
  'component_value_fetch',
  'component_value_cleanup'
];

export const UPLOADED_FILE_PARSE_MERGE_GROUP = [
  'file_upload',
  'activity_file_parse'
];

export const UPLOADED_DATA_PROCESSING_MERGE_GROUP = [
  'uploaded_component_value_extract',
  'component_value_cleanup'
];

export function isSingleActivityTrace(steps) {
  return steps.some((step) => (
    step?.payload?.workflow_mode === 'single_activity_outbound_first'
    || stepKey(step) === 'outbound_activity_data_fetch'
  ));
}

// 单活动场景额外把“外呼活动数据查询”并入合并步骤
export function dataPipelineMergeGroup(steps) {
  return isSingleActivityTrace(steps)
    ? ['outbound_activity_data_fetch', ...DATA_PIPELINE_MERGE_GROUP]
    : DATA_PIPELINE_MERGE_GROUP;
}

export function buildMergedDataPipelineStep(group) {
  return buildMergedTraceStep(
    group,
    'data_pipeline_merged',
    '数据获取、处理与分析',
    '正在获取活动数据并实时匹配分析组件、计算指标...'
  );
}

export function buildMergedTraceStep(group, node, displayName, runningMessage) {
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
export function mergeDataPipelineSteps(sortedSteps, mergeGroup) {
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

export function isUploadedActivityTrace(steps) {
  return steps.some((step) => (
    stepKey(step) === 'uploaded_component_value_extract'
    || stepKey(step) === 'activity_file_parse'
    || step?.payload?.uploaded_activity_dataset
  ));
}

export function mergeUploadedActivityTraceSteps(sortedSteps) {
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
      ...(payload.component_value_fetch_summary ? { component_value_fetch_summary: payload.component_value_fetch_summary } : {}),
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

export function activityTemplateMatchResult(step) {
  if (isPendingStep(step)) return null;
  return step?.payload?.activity_template_match_result || null;
}

// 组件数值获取摘要（后端 _step_trace_payload 注入 component_value_fetch_summary）：
// template_list_fetch/template_matching/component_value_fetch/component_value_cleanup
// 合并为 data_pipeline_merged 步骤后 payload 随之合并，按 payload 判断而非节点名。
export function componentValueFetchSummary(step) {
  if (isPendingStep(step)) return null;
  const summary = step?.payload?.component_value_fetch_summary;
  if (!summary) return null;
  return (summary.metric_count > 0 || summary.error_count > 0) ? summary : null;
}

export function componentValueCleanupResult(step) {
  if (isPendingStep(step)) return null;
  return step?.payload?.component_value_cleanup_result || null;
}

export function componentValueCleanupText(step) {
  const result = componentValueCleanupResult(step);
  if (!result) return '';
  const removedValues = Number(result.removed_values) || 0;
  const removedParams = Number(result.removed_params) || 0;
  if (!removedValues && !removedParams) return '数据完整，无需清理';
  const parts = [];
  if (removedValues) parts.push(`清理空指标 ${removedValues} 项`);
  if (removedParams) parts.push(`清理空参数 ${removedParams} 项`);
  return parts.join('，');
}

// 数据模板匹配/分析能力清单不再在思维面板展示（报告页与 /chat-ui 均改为展示
// 组件数值获取与数据清理的真实步骤数据），templateMatchResult /
// templateMatchCandidates / templateListNames / showTemplateMatchDetail /
// showTemplateListDetail 已随展示块一并移除。

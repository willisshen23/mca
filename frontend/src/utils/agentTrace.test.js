import { describe, it, expect } from 'vitest';
import {
  visibleTraceSteps,
  traceProgressText,
  finishThinkingTrace,
  stepStatusText,
  traceDisplayName,
  upsertTraceStep,
  shouldDisplayThinkingTrace
} from './agentTrace.js';

function makeStep(node, status, extra = {}) {
  return { node, displayName: node, message: '', status, timestamp: 1, ...extra };
}

describe('agentTrace', () => {
  it('traceDisplayName 使用中文显示名', () => {
    expect(traceDisplayName('intent_recognition')).toBe('意图识别');
    expect(traceDisplayName('unknown_node', '', '兜底')).toBe('兜底');
  });

  it('stepStatusText 覆盖各状态', () => {
    expect(stepStatusText('done')).toBe('已完成');
    expect(stepStatusText('running')).toBe('执行中');
    expect(stepStatusText('failed')).toBe('执行失败');
    expect(stepStatusText('skipped')).toBe('已跳过');
    expect(stepStatusText('pending')).toBe('待执行');
  });

  it('visibleTraceSteps 将数据管线步骤合并为一个展示步骤', () => {
    const steps = [
      makeStep('intent_recognition', 'done'),
      makeStep('template_list_fetch', 'done'),
      makeStep('template_matching', 'running'),
      makeStep('component_value_fetch', 'pending'),
      makeStep('component_value_cleanup', 'pending'),
      makeStep('marketing_report_synthesis', 'pending')
    ];
    const visible = visibleTraceSteps({ steps });
    const merged = visible.find((s) => s.node === 'data_pipeline_merged');
    expect(merged).toBeTruthy();
    expect(merged.displayName).toBe('数据获取、处理与分析');
    expect(merged.status).toBe('running');
    // 合并后不再出现原子步骤
    expect(visible.some((s) => s.node === 'template_matching')).toBe(false);
  });

  it('visibleTraceSteps 隐藏 guard 步骤与 supervisor/finalize', () => {
    const steps = [
      makeStep('intent_recognition', 'done'),
      makeStep('report_html_guard', 'done'),
      makeStep('supervisor', 'done'),
      makeStep('finalize', 'done')
    ];
    const visible = visibleTraceSteps({ steps });
    expect(visible.map((s) => s.node)).toEqual(['intent_recognition']);
  });

  it('finishThinkingTrace 将 pending 步骤标记为 skipped', () => {
    const trace = {
      status: 'running',
      startedAt: Date.now() - 100,
      steps: [makeStep('intent_recognition', 'done'), makeStep('report_generation', 'pending')]
    };
    finishThinkingTrace(trace, {});
    expect(trace.status).toBe('done');
    expect(trace.steps[1].status).toBe('skipped');
    expect(trace.steps[1].skipReason).toBeTruthy();
  });

  it('finishThinkingTrace 等待审批时状态为 paused', () => {
    const trace = { status: 'running', startedAt: Date.now() - 100, steps: [] };
    finishThinkingTrace(trace, { awaiting_approval: true });
    expect(trace.status).toBe('paused');
  });

  it('traceProgressText 统计可见步骤进度', () => {
    const message = {
      status: 'running',
      steps: [makeStep('intent_recognition', 'done'), makeStep('marketing_data_fetch', 'running')]
    };
    expect(traceProgressText(message)).toBe('2/2');
  });

  it('upsertTraceStep 按 key 更新已有步骤并合并 payload', () => {
    const trace = { steps: [{ node: 'intent_recognition', status: 'running', payload: { a: 1 }, timestamp: 1 }] };
    upsertTraceStep(trace, { node: 'intent_recognition', status: 'done', payload: { b: 2 }, timestamp: 2 });
    expect(trace.steps).toHaveLength(1);
    expect(trace.steps[0].status).toBe('done');
    expect(trace.steps[0].payload).toEqual({ a: 1, b: 2 });
  });

  it('shouldDisplayThinkingTrace 空步骤不展示', () => {
    expect(shouldDisplayThinkingTrace({ status: 'done', steps: [] })).toBe(false);
    expect(shouldDisplayThinkingTrace({ status: 'running', steps: [makeStep('intent_recognition', 'running')] })).toBe(true);
  });
});

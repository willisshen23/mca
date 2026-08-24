import { describe, it, expect } from 'vitest';
import {
  activityName, activityId, activityRowNumber, activityPeriod,
  compactActivity, selectedActivityRowNumbers, toggleActivitySelectionPure,
  selectionActivities, allActivitySelectionChecked, selectableActivityRowCount
} from './activityFormat.js';

describe('activityFormat', () => {
  it('activityName 兼容多种字段', () => {
    expect(activityName({ name: '薪运活动' })).toBe('薪运活动');
    expect(activityName({ actName: '代发活动' })).toBe('代发活动');
    expect(activityName({ '活动名称': '开门红' })).toBe('开门红');
    expect(activityName({})).toBe('未命名活动');
  });

  it('activityId 兼容多种字段', () => {
    expect(activityId({ activity_id: 'A001' })).toBe('A001');
    expect(activityId({ actNo: 'B002' })).toBe('B002');
    expect(activityId({ '活动编号': 'C003' })).toBe('C003');
  });

  it('activityRowNumber 非法值回退为索引+1', () => {
    expect(activityRowNumber({ row_number: 3 })).toBe(3);
    expect(activityRowNumber({}, 4)).toBe(5);
    expect(activityRowNumber({ row_number: 'x' }, 0)).toBe(1);
  });

  it('activityPeriod 拼接起止日期', () => {
    expect(activityPeriod({ start_date: '2024-01-01', end_date: '2024-03-31' })).toBe('2024-01-01 至 2024-03-31');
    expect(activityPeriod({})).toBe('');
  });

  it('compactActivity 提取核心字段', () => {
    const compact = compactActivity({ row_number: 2, activity_id: 'A1', name: '活动', channel: '短信', content: '内容' });
    expect(compact).toMatchObject({ row_number: 2, activity_id: 'A1', name: '活动', channel: '短信', content: '内容' });
  });

  it('toggleActivitySelectionPure 切换选中状态', () => {
    const message = { selectedIds: [] };
    const activity = { activity_id: 'A1' };
    toggleActivitySelectionPure(message, activity);
    expect(message.selectedIds).toEqual(['A1']);
    toggleActivitySelectionPure(message, activity);
    expect(message.selectedIds).toEqual([]);
  });

  it('selectedActivityRowNumbers 返回选中行号', () => {
    const message = {
      selectableActivities: [{ activity_id: 'A1', row_number: 1 }, { activity_id: 'A2', row_number: 2 }],
      selectedIds: ['A2']
    };
    expect(selectedActivityRowNumbers(message)).toEqual([2]);
  });

  it('allActivitySelectionChecked 判断全选', () => {
    const message = {
      selectableActivities: [{ activity_id: 'A1' }, { activity_id: 'A2' }],
      selectedIds: ['A1', 'A2']
    };
    expect(allActivitySelectionChecked(message)).toBe(true);
    expect(selectionActivities({ activities: [{ activity_id: 'A1' }] })).toHaveLength(1);
  });

  it('selectableActivityRowCount 识别正文中的可选活动表格', () => {
    const text = [
      '查到以下活动：',
      '| 序号 | 活动名称 | 渠道 |',
      '| --- | --- | --- |',
      '| 1 | 活动A | 短信 |',
      '| 2 | 活动B | 外呼 |',
      '| 3 | 活动C | 短信 |',
      '请选择要分析的活动。'
    ].join('\n');
    expect(selectableActivityRowCount({ text })).toBe(3);
  });

  it('selectableActivityRowCount 决策类纯文字提问返回 0', () => {
    // 业务状态里即使有 activity_list，正文无表格就不可选
    const message = {
      text: '请问您希望：\n1. 按外呼视角分析该活动；\n2. 补充其他活动一起分析？',
      selectableActivities: [{ activity_id: 'A1' }, { activity_id: 'A2' }]
    };
    expect(selectableActivityRowCount(message)).toBe(0);
    expect(selectableActivityRowCount({})).toBe(0);
    expect(selectableActivityRowCount(null)).toBe(0);
  });

  it('selectableActivityRowCount 忽略非活动表格与非序号表格', () => {
    const noActivityColumn = [
      '| 序号 | 步骤 | 说明 |',
      '| --- | --- | --- |',
      '| 1 | 取数 | xxx |'
    ].join('\n');
    expect(selectableActivityRowCount({ text: noActivityColumn })).toBe(0);
    const noRowNumberFirst = [
      '| 活动名称 | 序号 |',
      '| --- | --- |',
      '| 活动A | 1 |'
    ].join('\n');
    expect(selectableActivityRowCount({ text: noRowNumberFirst })).toBe(0);
  });
});

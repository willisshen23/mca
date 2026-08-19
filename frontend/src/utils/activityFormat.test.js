import { describe, it, expect } from 'vitest';
import {
  activityName, activityId, activityRowNumber, activityPeriod,
  compactActivity, selectedActivityRowNumbers, toggleActivitySelectionPure,
  selectionActivities, allActivitySelectionChecked
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
});

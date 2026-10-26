// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/api/agentRun.js', () => ({
  runAgentV2: vi.fn(),
  steerAgentV2: vi.fn(),
  cancelAgentV2: vi.fn(),
  resumeAgentV2: vi.fn(),
  getAgentV2RunStatus: vi.fn(),
  attachAgentV2Run: vi.fn()
}));
vi.mock('@/api/conversations.js', () => ({
  fetchConversationMessages: vi.fn(),
  createConversationAPI: vi.fn(),
  renameConversationAPI: vi.fn(),
  getUserId: vi.fn(() => 'test-user')
}));
vi.mock('@/api/agentRunHistory.js', () => ({
  submitReportFeedback: vi.fn(),
  reportDownloadUrl: vi.fn(() => '')
}));

import { useAgentChat } from './useAgentChat.js';
import { getAgentV2RunStatus, runAgentV2, steerAgentV2 } from '@/api/agentRun.js';

function makeConversation() {
  return {
    id: 'thread-1',
    title: '测试会话',
    typing: false,
    dynamicMessages: [
      { role: 'user', text: '将报告内容翻译成英文' },
      {
        role: 'approval_request',
        tool: 'modify_report',
        displayName: '修改报告',
        args: {},
        activities: [],
        description: '即将把报告全部内容翻译为英文',
        allowedDecisions: ['approve', 'edit', 'reject'],
        resolved: false,
        decision: null
      },
      { role: 'ai', text: '报告内容已翻译为英文（版本 v2）。' }
    ]
  };
}

describe('useAgentChat 刷新后的审批状态对账', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('服务端无待决审批时，残留的未决审批卡片被移除，输入框解除锁定', async () => {
    const conversation = makeConversation();
    const chat = useAgentChat({ getConversation: () => conversation });
    getAgentV2RunStatus.mockResolvedValue({
      exists: false, active: false, last_seq: 0, pending_approval: false
    });

    await chat.recoverAgentRun(conversation);

    expect(
      conversation.dynamicMessages.some((m) => m.role === 'approval_request' && !m.resolved)
    ).toBe(false);
    expect(chat.hasPendingApproval.value).toBe(false);
    // 持久化结果同样不含未决审批卡片，避免下次刷新再次复活
    const persisted = JSON.parse(localStorage.getItem('chat_dynamic_messages:thread-1') || '[]');
    expect(persisted.some((m) => m.role === 'approval_request')).toBe(false);
    // 其余消息不受影响
    expect(conversation.dynamicMessages.filter((m) => m.role !== 'approval_request')).toHaveLength(2);
  });

  it('服务端仍有待决审批时，保留未决审批卡片（用户可继续审批）', async () => {
    const conversation = makeConversation();
    const chat = useAgentChat({ getConversation: () => conversation });
    getAgentV2RunStatus.mockResolvedValue({
      exists: false, active: false, last_seq: 0, pending_approval: true
    });

    await chat.recoverAgentRun(conversation);

    expect(
      conversation.dynamicMessages.some((m) => m.role === 'approval_request' && !m.resolved)
    ).toBe(true);
    expect(chat.hasPendingApproval.value).toBe(true);
  });

  it('旧版服务端未返回 pending_approval 字段时保持现状，不误删卡片', async () => {
    const conversation = makeConversation();
    const chat = useAgentChat({ getConversation: () => conversation });
    getAgentV2RunStatus.mockResolvedValue({ exists: false, active: false, last_seq: 0 });

    await chat.recoverAgentRun(conversation);

    expect(
      conversation.dynamicMessages.some((m) => m.role === 'approval_request' && !m.resolved)
    ).toBe(true);
  });
});

describe('useAgentChat 执行中插话（steer）', () => {
  const encoder = new TextEncoder();

  function sseBody(events, { hang = false, signal = null } = {}) {
    let cursor = 0;
    return {
      getReader() {
        return {
          read() {
            if (cursor < events.length) {
              const value = encoder.encode(events[cursor]);
              cursor += 1;
              return Promise.resolve({ done: false, value });
            }
            if (hang) {
              return new Promise((resolve, reject) => {
                signal?.addEventListener('abort', () => {
                  reject(new DOMException('Aborted', 'AbortError'));
                });
              });
            }
            return Promise.resolve({ done: true, value: undefined });
          }
        };
      }
    };
  }

  function makeRunningConversation() {
    return {
      id: 'thread-steer',
      title: '插话测试',
      typing: false,
      dynamicMessages: []
    };
  }

  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('任务执行中发送插话走 steerAgentV2，旧流静默退出不干扰新流', async () => {
    const conversation = makeRunningConversation();
    const chat = useAgentChat({ getConversation: () => conversation });

    // 首轮：挂起的流（模拟长任务），并捕获其 AbortSignal
    let firstSignal = null;
    runAgentV2.mockImplementation(({ signal }) => {
      firstSignal = signal;
      return Promise.resolve({ ok: true, body: sseBody([], { hang: true, signal }) });
    });
    const firstSend = chat.sendMessage({ text: '分析三季度外呼活动', conversation });
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(conversation.typing).toBe(true);
    expect(runAgentV2).toHaveBeenCalledTimes(1);

    // 插话：steer 流直接给 done 帧
    steerAgentV2.mockResolvedValue({
      ok: true,
      body: sseBody(['data: {"type":"done","payload":{"final_response":"已按新指令调整"}}\n\n'])
    });
    await chat.sendMessage({ text: '等等，把国庆预热活动并进来', conversation });

    expect(steerAgentV2).toHaveBeenCalledTimes(1);
    expect(steerAgentV2.mock.calls[0][0].message).toBe('等等，把国庆预热活动并进来');
    // 旧 fetch 被中止
    expect(firstSignal.aborted).toBe(true);
    // 新流的 done 正常落地：回复入库、typing 复位
    expect(conversation.typing).toBe(false);
    const aiMessages = conversation.dynamicMessages.filter((m) => m.role === 'ai');
    expect(aiMessages.some((m) => m.text === '已按新指令调整')).toBe(true);
    // 旧流不得塞入"任务已取消。"之类的终态消息
    expect(aiMessages.some((m) => m.text.includes('任务已取消'))).toBe(false);
    await firstSend;
  });

  it('非执行中发送仍走 runAgentV2（不回退 steer）', async () => {
    const conversation = makeRunningConversation();
    const chat = useAgentChat({ getConversation: () => conversation });

    runAgentV2.mockResolvedValue({
      ok: true,
      body: sseBody(['data: {"type":"done","payload":{"final_response":"完成"}}\n\n'])
    });
    await chat.sendMessage({ text: '分析一下活动', conversation });

    expect(runAgentV2).toHaveBeenCalledTimes(1);
    expect(steerAgentV2).not.toHaveBeenCalled();
    expect(conversation.typing).toBe(false);
  });

  it('执行中无文本（仅附件/行选择）不触发插话', async () => {
    const conversation = makeRunningConversation();
    conversation.typing = true;
    const chat = useAgentChat({ getConversation: () => conversation });

    await chat.sendMessage({ text: '', conversation });

    expect(steerAgentV2).not.toHaveBeenCalled();
    expect(runAgentV2).not.toHaveBeenCalled();
  });
});

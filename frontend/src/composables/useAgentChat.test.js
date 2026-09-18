// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/api/agentRun.js', () => ({
  runAgentV2: vi.fn(),
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
import { getAgentV2RunStatus } from '@/api/agentRun.js';

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

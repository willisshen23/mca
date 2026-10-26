import { API_BASE } from './base.js';
import { getUserId } from './conversations.js';

// agent_v2（deepagents）对话接口。

function getSrcSysNo() {
  return (localStorage.getItem('src_sys_no') || '').trim();
}

export async function runAgentV2({
  threadId,
  message,
  originalUserText = '',
  filePath = '',
  userId = '',
  userName = '',
  orgNo = '',
  srcSysNo = '',
  channel = '',
  reportComponents = [],
  signal
}) {
  // 返回原始 response，由调用方按 SSE 流读取。
  return fetch(`${API_BASE}/v2/agent/run`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getUserId()
    },
    body: JSON.stringify({
      thread_id: threadId,
      message,
      original_user_text: originalUserText,
      file_path: filePath,
      user_id: userId || getUserId(),
      user_name: userName,
      org_no: orgNo,
      src_sys_no: srcSysNo || getSrcSysNo(),
      channel,
      // 报告页组件编排预选的分析组件；/chat-ui 传空数组，后端走原模板匹配流程
      report_components: reportComponents
    }),
    signal
  });
}

// 任意时刻插话：打断当前 run，以插话为新指令带 checkpoint 续跑。
// 仅当会话有活跃任务时可用（无活跃任务后端会报错，前端应直接走 runAgentV2）。
export async function steerAgentV2({
  threadId,
  message,
  originalUserText = '',
  userId = '',
  userName = '',
  orgNo = '',
  srcSysNo = '',
  channel = '',
  signal
}) {
  return fetch(`${API_BASE}/v2/agent/steer`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getUserId()
    },
    body: JSON.stringify({
      thread_id: threadId,
      message,
      original_user_text: originalUserText,
      user_id: userId || getUserId(),
      user_name: userName,
      org_no: orgNo,
      src_sys_no: srcSysNo || getSrcSysNo(),
      channel
    }),
    signal
  });
}

export async function resumeAgentV2({
  threadId,
  decision,
  tool = '',
  editedArgs = {},
  message = '',
  userId = '',
  userName = '',
  orgNo = '',
  srcSysNo = '',
  channel = ''
}) {
  return fetch(`${API_BASE}/v2/agent/resume`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getUserId()
    },
    body: JSON.stringify({
      thread_id: threadId,
      decision,
      tool,
      edited_args: editedArgs,
      message,
      user_id: userId || getUserId(),
      user_name: userName,
      org_no: orgNo,
      src_sys_no: srcSysNo || getSrcSysNo(),
      channel
    })
  });
}

export async function cancelAgentV2(threadId) {
  const response = await fetch(`${API_BASE}/v2/agent/cancel`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': getUserId()
    },
    body: JSON.stringify({ thread_id: threadId })
  });
  if (!response.ok) {
    throw new Error(`取消失败：${response.status}`);
  }
  return response.json();
}

export async function getAgentV2RunStatus(threadId) {
  const response = await fetch(`${API_BASE}/v2/agent/runs/${encodeURIComponent(threadId)}`, {
    headers: { 'X-User-Id': getUserId() }
  });
  if (!response.ok) {
    throw new Error(`查询任务状态失败：${response.status}`);
  }
  return response.json();
}

export async function attachAgentV2Run(threadId, after = 0) {
  return fetch(
    `${API_BASE}/v2/agent/runs/${encodeURIComponent(threadId)}/stream?after=${Math.max(0, Number(after) || 0)}`,
    { headers: { 'X-User-Id': getUserId() } }
  );
}

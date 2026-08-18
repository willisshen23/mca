const ACTIVITY_TYPE_LABELS = {
  A: 'H5活动',
  B: '画布活动',
  C: '大零售活动',
  D: '外部活动',
  Y: '策略中心'
};

const ACTIVITY_STATUS_LABELS = {
  A1: '已删除',
  A2: '未提交',
  A3: '已上线',
  A6: '已下线',
  A7: '审批中',
  A8: '审批通过',
  A9: '审批驳回',
  B01: '策划',
  B02: '待审批',
  B03: '待执行',
  B04: '执行中',
  B05: '暂停',
  B06: '已结束',
  B07: '提前下线',
  C0: '未查看',
  C3: '发布中',
  C4: '终止',
  C5: '过期关闭',
  C6: '提前终止',
  D1: '上线',
  D0: '下线',
  Y0: '草稿',
  Y1: '已发布',
  Y2: '一级审批通过',
  Y3: '审批通过',
  Y4: '审批不通过',
  Y5: '审批超时',
  Y6: '进行中',
  Y7: '提前终止',
  Y8: '活动结束'
};

function cleanValue(value) {
  return String(value ?? '').trim();
}

function normalizeCode(value) {
  return cleanValue(value).toUpperCase();
}

function stripScope(value) {
  return cleanValue(value)
    .replace(/\s*[（(][^）)]*[）)]\s*$/u, '')
    .trim();
}

function inferTypeCodeFromStatus(status) {
  const code = normalizeCode(status);
  if (!code) return '';
  if (code.startsWith('B')) return 'B';
  return ACTIVITY_TYPE_LABELS[code[0]] ? code[0] : '';
}

export function displayActivityType(type, status = '') {
  const raw = cleanValue(type);
  const code = normalizeCode(raw);
  if (ACTIVITY_TYPE_LABELS[code]) return ACTIVITY_TYPE_LABELS[code];
  if (ACTIVITY_STATUS_LABELS[code] && ACTIVITY_TYPE_LABELS[code[0]]) return ACTIVITY_TYPE_LABELS[code[0]];

  const inferredCode = inferTypeCodeFromStatus(status);
  if (!raw && inferredCode) return ACTIVITY_TYPE_LABELS[inferredCode];
  return stripScope(raw);
}

export function displayActivityStatus(status) {
  const raw = cleanValue(status);
  const code = normalizeCode(raw);
  return ACTIVITY_STATUS_LABELS[code] || stripScope(raw);
}

const ACTIVITY_STATUS_CODE_PATTERN = Object.keys(ACTIVITY_STATUS_LABELS)
  .sort((left, right) => right.length - left.length)
  .join('|');

/** 替换自然语言中的独立活动状态码，活动编号内部的同名片段保持不变。 */
export function replaceActivityStatusCodes(text) {
  const standaloneCode = new RegExp(
    `(^|[^A-Za-z0-9_-])(${ACTIVITY_STATUS_CODE_PATTERN})(?=$|[^A-Za-z0-9_-])`,
    'gi'
  );
  return String(text ?? '').replace(
    standaloneCode,
    (_match, prefix, code) => `${prefix}${displayActivityStatus(code)}`
  );
}

export function activityStatusTone(status) {
  const label = displayActivityStatus(status);
  if (/审批不通过|审批驳回|审批超时/.test(label)) return 'danger';
  if (/进行中|执行中|已上线|上线|发布中|已发布/.test(label)) return 'active';
  if (/结束|终止|下线|关闭|删除/.test(label)) return 'closed';
  if (/待|审批|草稿|策划|未提交|暂停|未查看/.test(label)) return 'pending';
  return 'neutral';
}

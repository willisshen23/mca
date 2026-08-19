import { computed, reactive } from 'vue';
import { skillData } from '../data/mockData';

export const REPORT_SESSION_KEY = 'report_page_session';

const state = reactive({
  currentType: 'online',
  selectedActivityNames: new Set(),
  offlineFile: null,
  offlineStart: '',
  offlineEnd: '',
  canvasComps: skillData.slice(0, 5).map((item) => ({ ...item })),
  defaultCanvasComps: skillData.slice(0, 5).map((item) => ({ ...item })),
  canvasInitializedFromApi: false,
  activeTemplateName: '',
  s2Messages: [
    { role: 'ai', text: '已加载默认分析框架，支持拖拽排序、双击添加、上下移动按钮。' }
  ],
  s3Messages: [
    { role: 'ai', text: '报告已生成，可针对报告提问。' }
  ]
});

function cloneSkill(skill) {
  return { name: skill.name, cat: skill.cat, desc: skill.desc, tpl: skill.tpl };
}

export function useAnalysisStore() {
  const selectedCount = computed(() => state.selectedActivityNames.size);
  const canGoNext = computed(() => {
    if (state.currentType === 'online') {
      return state.selectedActivityNames.size > 0;
    }
    return Boolean(state.offlineFile?.file_path && state.offlineStart && state.offlineEnd && state.offlineStart <= state.offlineEnd);
  });
  const lockSummary = computed(() => ({
    typeName: state.currentType === 'online' ? '线上活动' : '线下活动',
    source: state.currentType === 'online'
      ? `${state.selectedActivityNames.size || 3}项线上活动`
      : state.offlineFile?.file_name || '线下活动数据',
    period: state.currentType === 'online' ? '2024-01-01 至 2024-03-31' : `${state.offlineStart || '2024-01-01'} 至 ${state.offlineEnd || '2024-03-31'}`
  }));
  const reportTitle = computed(() => (
    state.currentType === 'online'
      ? '2024年Q1线上活动分析报告'
      : '2024年线下活动综合分析报告'
  ));

  function setAnalysisType(type, shouldReset = false) {
    state.currentType = type === 'offline' ? 'offline' : 'online';
    if (shouldReset) {
      state.selectedActivityNames.clear();
      state.offlineFile = null;
      state.offlineStart = '';
      state.offlineEnd = '';
    }
  }

  function toggleActivity(activityName) {
    if (state.selectedActivityNames.has(activityName)) {
      state.selectedActivityNames.delete(activityName);
    } else {
      state.selectedActivityNames.add(activityName);
    }
  }

  function setAllActivities(checked, activities = []) {
    state.selectedActivityNames.clear();
    if (checked) {
      activities.forEach((activity) => state.selectedActivityNames.add(activity.name));
    }
  }

  function setOfflineDates(start, end) {
    state.offlineStart = start;
    state.offlineEnd = end;
  }

  function setOfflineFile(fileInfo) {
    state.offlineFile = fileInfo ? {
      file_name: fileInfo.file_name || '',
      file_path: fileInfo.file_path || '',
      size: fileInfo.size || 0
    } : null;
  }

  function clearOfflineFile() {
    state.offlineFile = null;
  }

  function resetReportSession() {
    try {
      localStorage.removeItem(REPORT_SESSION_KEY);
    } catch (e) {
      console.warn('清除报告会话失败', e);
    }
  }

  function addCanvasSkill(skill) {
    state.canvasComps.push(cloneSkill(skill));
    addS2Message('ai', `已添加「${skill.name}」至分析框架。`);
  }

  function removeCanvasSkill(index) {
    state.canvasComps.splice(index, 1);
  }

  function moveCanvasSkill(index, direction) {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= state.canvasComps.length) return;
    const movedName = state.canvasComps[index].name;
    [state.canvasComps[index], state.canvasComps[nextIndex]] = [state.canvasComps[nextIndex], state.canvasComps[index]];
    addS2Message('ai', `已将「${movedName}」${direction < 0 ? '上移' : '下移'}。`);
  }

  function reorderCanvasSkill(from, to) {
    if (from === to || from < 0 || to < 0 || from >= state.canvasComps.length || to >= state.canvasComps.length) return;
    const [moved] = state.canvasComps.splice(from, 1);
    state.canvasComps.splice(to, 0, moved);
    addS2Message('ai', '组件顺序已调整。');
  }

  function resetCanvas() {
    state.canvasComps.splice(0, state.canvasComps.length, ...state.defaultCanvasComps.map(cloneSkill));
    state.activeTemplateName = '';
    addS2Message('ai', '已重置为默认分析框架。');
  }

  function applyTemplateToCanvas(skills, templateName = '') {
    state.canvasComps.splice(0, state.canvasComps.length, ...skills.map(cloneSkill));
    state.activeTemplateName = templateName;
    addS2Message('ai', templateName ? `已应用模板「${templateName}」，分析组件已替换。` : '分析组件已更新。');
  }

  function setCanvasDefaults(skills) {
    const defaults = skills.slice(0, 5).map(cloneSkill);
    if (defaults.length === 0) return;
    state.defaultCanvasComps.splice(0, state.defaultCanvasComps.length, ...defaults);
    if (!state.canvasInitializedFromApi) {
      state.canvasComps.splice(0, state.canvasComps.length, ...defaults.map(cloneSkill));
      state.canvasInitializedFromApi = true;
    }
  }

  function addS2Message(role, text) {
    state.s2Messages.push({ role, text });
  }

  function addS3Message(role, text) {
    state.s3Messages.push({ role, text });
  }

  return {
    state,
    selectedCount,
    canGoNext,
    lockSummary,
    reportTitle,
    setAnalysisType,
    toggleActivity,
    setAllActivities,
    setOfflineDates,
    setOfflineFile,
    clearOfflineFile,
    resetReportSession,
    addCanvasSkill,
    removeCanvasSkill,
    moveCanvasSkill,
    reorderCanvasSkill,
    resetCanvas,
    applyTemplateToCanvas,
    setCanvasDefaults,
    addS2Message,
    addS3Message
  };
}

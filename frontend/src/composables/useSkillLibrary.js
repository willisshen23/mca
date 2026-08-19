import { computed, ref } from 'vue';
import { fetchSkills } from '@/api/skills.js';

// 管理后台 SKILL 库的前端缓存：思维过程面板展示 SKILL 详情时，
// 运行时 payload 未携带的字段（分类/描述/展示模板）从这里按名称兜底补齐。
const skills = ref([]);
const loaded = ref(false);
let loadingPromise = null;

const skillIndex = computed(() => {
  const index = new Map();
  for (const skill of skills.value) {
    const name = String(skill?.name || '').trim();
    if (name && !index.has(name)) index.set(name, skill);
  }
  return index;
});

export function useSkillLibrary() {
  function ensureLoaded() {
    if (loaded.value) return Promise.resolve(skills.value);
    if (!loadingPromise) {
      loadingPromise = fetchSkills()
        .then((list) => {
          skills.value = Array.isArray(list) ? list : [];
          loaded.value = true;
          return skills.value;
        })
        .catch((error) => {
          // 兜底数据加载失败不阻塞思维面板渲染，payload 自带详情仍可展示
          console.warn('加载 SKILL 库失败', error);
          loadingPromise = null;
          return [];
        });
    }
    return loadingPromise;
  }

  function skillByName(name) {
    const key = String(name || '').trim();
    return key ? skillIndex.value.get(key) || null : null;
  }

  return { skills, loaded, ensureLoaded, skillByName };
}

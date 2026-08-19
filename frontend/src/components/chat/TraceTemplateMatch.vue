<script setup>
import { computed, onMounted } from 'vue';
import { useSkillLibrary } from '@/composables/useSkillLibrary.js';

// 思维过程面板中的「分析模板匹配结果」卡片：
// 主模板（名称/ID/匹配度/理由）+ Top-N 候选 + 有序 SKILL 编排（分类/描述/展示要求）。
const props = defineProps({
  label: { type: String, default: '分析模板匹配' },
  result: { type: Object, default: null },
  candidates: { type: Array, default: () => [] },
  pending: { type: Boolean, default: false },
  emptyText: { type: String, default: '已完成匹配' }
});

const { ensureLoaded, skillByName } = useSkillLibrary();
onMounted(() => {
  // 预载管理后台 SKILL 库，payload 未携带的详情按名称兜底补齐
  ensureLoaded();
});

function similarityPercent(template) {
  const score = Number(template?.similarity_score);
  if (!Number.isFinite(score)) return null;
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}

const primaryPercent = computed(() => similarityPercent(props.result));

// 其余候选模板（第一位即主匹配，不重复展示）
const extraCandidates = computed(() =>
  (Array.isArray(props.candidates) ? props.candidates : []).slice(1)
);

function normalizeCard(raw, index) {
  return {
    key: `${raw.position || index + 1}:${raw.name || raw.skill_name || index}`,
    position: raw.position || index + 1,
    name: raw.display_name || raw.name || raw.skill_name || '',
    skill_category: raw.skill_category || '',
    skill_description: raw.skill_description || '',
    skill_template_preview: raw.skill_template_preview || '',
    metrics: Array.isArray(raw.metrics) ? raw.metrics.filter(Boolean) : []
  };
}

// 有序 SKILL 编排：dependent_components 优先，skill_sequence 兜底；
// 再用管理后台 SKILL 库补齐缺失的分类/描述/展示模板。
const skillCards = computed(() => {
  const source = props.result;
  if (!source) return [];
  let cards = [];
  const components = Array.isArray(source.dependent_components) ? source.dependent_components : [];
  if (components.length) {
    cards = components.map((item, index) => normalizeCard(item, index));
  } else {
    const sequence = Array.isArray(source.skill_sequence) ? source.skill_sequence : [];
    cards = sequence.map((item, index) => normalizeCard(
      typeof item === 'string' ? { name: item } : (item || {}),
      index
    ));
  }
  return cards
    .filter((card) => card.name)
    .map((card) => {
      const lib = skillByName(card.name);
      if (!lib) return card;
      return {
        ...card,
        skill_category: card.skill_category || lib.cat || '',
        skill_description: card.skill_description || lib.desc || '',
        skill_template_preview: card.skill_template_preview || lib.tpl || ''
      };
    });
});
</script>

<template>
  <div class="trace-step-detail tpl-match">
    <div class="detail-label">{{ label }}</div>
    <div v-if="pending" class="detail-value">等待执行</div>
    <template v-else-if="result">
      <div class="tpl-match-card">
        <div class="tpl-match-head">
          <span class="tpl-match-name">{{ result.template_name || '未命名模板' }}</span>
          <span v-if="result.template_id" class="tpl-match-id">{{ result.template_id }}</span>
        </div>
        <div v-if="primaryPercent !== null" class="tpl-score-row">
          <span class="tpl-score-label">匹配度</span>
          <div class="tpl-score-bar">
            <div class="tpl-score-fill" :style="{ width: `${primaryPercent}%` }"></div>
          </div>
          <span class="tpl-score-num">{{ primaryPercent }}%</span>
        </div>
        <div v-if="result.reasoning" class="tpl-reasoning">{{ result.reasoning }}</div>
      </div>

      <details v-if="extraCandidates.length" class="tpl-candidates">
        <summary>
          <i class="ti ti-chevron-right tpl-candidates-chevron" aria-hidden="true"></i>
          查看 {{ extraCandidates.length }} 个候选模板
        </summary>
        <div
          v-for="(candidate, candidateIndex) in extraCandidates"
          :key="candidate.template_id || candidate.template_name || candidateIndex"
          class="tpl-candidate-item"
        >
          <span class="tpl-candidate-rank">#{{ candidateIndex + 2 }}</span>
          <span class="tpl-candidate-name">{{ candidate.template_name || '未命名模板' }}</span>
          <span v-if="similarityPercent(candidate) !== null" class="tpl-candidate-score">
            {{ similarityPercent(candidate) }}%
          </span>
        </div>
      </details>

      <div v-if="skillCards.length" class="skill-flow">
        <div class="detail-label skill-flow-label">分析 SKILL 编排</div>
        <div v-for="card in skillCards" :key="card.key" class="skill-card">
          <div class="skill-card-head">
            <span class="skill-card-position">{{ card.position }}</span>
            <span class="skill-card-name">{{ card.name }}</span>
            <span v-if="card.skill_category" class="skill-card-cat">{{ card.skill_category }}</span>
          </div>
          <div v-if="card.skill_description" class="skill-card-desc">{{ card.skill_description }}</div>
          <div v-if="card.metrics.length" class="skill-card-metrics">
            <span v-for="metric in card.metrics" :key="metric" class="skill-card-metric">{{ metric }}</span>
          </div>
          <details v-if="card.skill_template_preview" class="skill-card-preview">
            <summary>
              <i class="ti ti-chevron-right tpl-candidates-chevron" aria-hidden="true"></i>
              展示要求
            </summary>
            <div class="skill-card-preview-body">{{ card.skill_template_preview }}</div>
          </details>
        </div>
      </div>
    </template>
    <div v-else class="detail-value">{{ emptyText }}</div>
  </div>
</template>

<style scoped>
/* 与思维面板其他详情块保持一致的容器/标签样式（父级样式为 scoped，需在组件内重新定义） */
.trace-step-detail { display: flex; flex-direction: column; margin-top: 6px; padding: 6px 10px; background: #fff; border-radius: 6px; border: .5px solid var(--BD); }
.detail-label { font-size: 10px; color: var(--T3); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 2px; }
.detail-value { font-size: 12px; color: var(--T1); font-weight: 500; }
.tpl-match { gap: 8px; }
.tpl-match-card { padding: 8px 10px; border: .5px solid var(--BD); border-radius: 8px; background: var(--BG); }
.tpl-match-head { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.tpl-match-name { flex: 1; min-width: 0; font-size: 12px; font-weight: 700; color: var(--T1); line-height: 1.45; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tpl-match-id { flex-shrink: 0; font-size: 10px; color: var(--T3); font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.tpl-score-row { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.tpl-score-label { flex-shrink: 0; font-size: 10px; color: var(--T3); letter-spacing: .5px; }
.tpl-score-bar { flex: 1; height: 6px; border-radius: 999px; background: #E5E6EB; overflow: hidden; }
.tpl-score-fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, #4E8DFF, var(--P)); transition: width .4s ease; }
.tpl-score-num { flex-shrink: 0; font-size: 11px; font-weight: 700; color: var(--P); font-variant-numeric: tabular-nums; }
.tpl-reasoning { margin-top: 6px; font-size: 11px; color: var(--T2); line-height: 1.55; }

.tpl-candidates { border: .5px solid var(--BD); border-radius: 8px; background: var(--BG); }
.tpl-candidates summary,
.skill-card-preview summary { display: flex; align-items: center; gap: 5px; padding: 6px 10px; font-size: 11px; font-weight: 600; color: var(--T2); cursor: pointer; list-style: none; user-select: none; }
.tpl-candidates summary::-webkit-details-marker,
.skill-card-preview summary::-webkit-details-marker { display: none; }
.tpl-candidates summary:hover,
.skill-card-preview summary:hover { color: var(--P); }
.tpl-candidates-chevron { font-size: 12px; transition: transform .15s ease; }
details[open] > summary .tpl-candidates-chevron { transform: rotate(90deg); }
.tpl-candidate-item { display: flex; align-items: center; gap: 8px; padding: 5px 10px; border-top: .5px dashed var(--BD); }
.tpl-candidate-rank { flex-shrink: 0; font-size: 10px; font-weight: 700; color: var(--T3); font-variant-numeric: tabular-nums; }
.tpl-candidate-name { flex: 1; min-width: 0; font-size: 11px; font-weight: 500; color: var(--T1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tpl-candidate-score { flex-shrink: 0; font-size: 11px; font-weight: 600; color: var(--T2); font-variant-numeric: tabular-nums; }

.skill-flow { display: flex; flex-direction: column; gap: 6px; }
.skill-flow-label { margin-top: 2px; }
.skill-card { padding: 7px 10px; border: .5px solid var(--BD); border-radius: 8px; background: var(--BG); }
.skill-card-head { display: flex; align-items: center; gap: 7px; min-width: 0; }
.skill-card-position { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; flex: 0 0 18px; border-radius: 50%; background: #eef3ff; color: var(--P); font-size: 10px; font-weight: 700; line-height: 1; }
.skill-card-name { flex: 1; min-width: 0; font-size: 12px; font-weight: 600; color: var(--T1); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.skill-card-cat { flex-shrink: 0; display: inline-flex; align-items: center; height: 18px; padding: 0 7px; border-radius: 999px; background: #f0fdfa; border: .5px solid #99f6e4; color: #0f766e; font-size: 10px; font-weight: 600; line-height: 1; white-space: nowrap; }
.skill-card-desc { margin-top: 4px; padding-left: 25px; font-size: 11px; color: var(--T2); line-height: 1.55; }
.skill-card-metrics { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 5px; padding-left: 25px; }
.skill-card-metric { display: inline-flex; align-items: center; height: 18px; padding: 0 7px; border-radius: 999px; background: #fff; border: .5px solid var(--BD); color: var(--T2); font-size: 10px; font-weight: 500; line-height: 1; white-space: nowrap; }
.skill-card-preview { margin-top: 5px; margin-left: 25px; border: .5px dashed var(--BD); border-radius: 6px; background: #fff; }
.skill-card-preview summary { padding: 4px 8px; font-size: 10px; }
.skill-card-preview-body { padding: 6px 8px; border-top: .5px dashed var(--BD); font-size: 11px; color: var(--T2); line-height: 1.6; white-space: pre-wrap; word-break: break-word; max-height: 180px; overflow: auto; }
</style>

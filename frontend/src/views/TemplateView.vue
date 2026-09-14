<script setup>
import { ref, reactive, computed, onMounted } from 'vue';
import ModalDialog from '../components/common/ModalDialog.vue';
import { useRouter } from 'vue-router';
import { useAnalysisStore } from '../stores/analysisStore';
import {
  applyActivityTemplate,
  createActivityTemplate,
  deleteActivityTemplate,
  fetchActivityTemplates,
  fetchSkills,
  updateActivityTemplate
} from '../api/skills';

const router = useRouter();
const store = useAnalysisStore();

const templates = ref([]);
const allSkills = ref([]);
const loading = ref(false);
const error = ref('');

const filterType = ref('全部类型');
const searchKeyword = ref('');
const activeModal = ref('');
const editingTplId = ref(null);
const viewingTplId = ref(null);
const deletingTplId = ref(null);

const newTemplate = reactive({
  name: '',
  type: '通用',
  desc: '',
  selectedSkills: []
});

const availableSkills = computed(() => allSkills.value.map((skill) => ({
  name: skill.name,
  cat: skill.cat,
  desc: skill.desc
})));

const filteredTemplates = computed(() => {
  return templates.value.filter(tpl => {
    const matchType = filterType.value === '全部类型' || 
      (filterType.value === '线上活动' && tpl.type === '线上活动') ||
      (filterType.value === '线下活动' && tpl.type === '线下活动') ||
      (filterType.value === '通用' && tpl.type === '通用');
    const matchKeyword = !searchKeyword.value.trim() || tpl.name.includes(searchKeyword.value.trim());
    return matchType && matchKeyword;
  });
});

const templateCount = computed(() => filteredTemplates.value.length);

const viewingTemplate = computed(() => {
  return templates.value.find(t => t.id === viewingTplId.value) || null;
});

async function loadData() {
  loading.value = true;
  error.value = '';
  try {
    const [templateList, skillList] = await Promise.all([
      fetchActivityTemplates(),
      fetchSkills()
    ]);
    templates.value = templateList;
    allSkills.value = skillList;
  } catch (err) {
    error.value = err.message || '模板数据加载失败';
  } finally {
    loading.value = false;
  }
}

function getTypeBadgeClass(type) {
  if (type === '线上活动') return 'tb2';
  if (type === '线下活动') return 'to';
  return 'tpur';
}

async function applyTemplate(template) {
  try {
    const updated = await applyActivityTemplate(template.id);
    const index = templates.value.findIndex((item) => item.id === template.id);
    if (index > -1) templates.value[index] = updated;
  } catch (err) {
    error.value = err.message || '应用模板失败';
    return;
  }
  const type = template.type === '线下活动' ? 'offline' : 'online';
  store.setAnalysisType(type, true);
  router.push({ name: 'source', params: { type } });
}

function openNewTemplateModal() {
  editingTplId.value = null;
  Object.assign(newTemplate, { name: '', type: '通用', desc: '', selectedSkills: [] });
  activeModal.value = 'new';
}

function openEditTemplateModal(tplId) {
  const tpl = templates.value.find(t => t.id === tplId);
  if (!tpl) return;
  editingTplId.value = tplId;
  Object.assign(newTemplate, { name: tpl.name, type: tpl.type || '通用', desc: tpl.desc, selectedSkills: [...tpl.skills] });
  activeModal.value = 'new';
}

function viewTemplateDetail(tplId) {
  viewingTplId.value = tplId;
  activeModal.value = 'detail';
}

function editTemplateFromDetail() {
  activeModal.value = '';
  if (viewingTplId.value) {
    openEditTemplateModal(viewingTplId.value);
  }
}

async function applyTemplateFromDetail() {
  if (viewingTemplate.value) {
    await applyTemplate(viewingTemplate.value);
    activeModal.value = '';
    viewingTplId.value = null;
  }
}

function toggleSkillSelection(skill) {
  const index = newTemplate.selectedSkills.findIndex(s => s === skill);
  if (index > -1) {
    newTemplate.selectedSkills.splice(index, 1);
  } else {
    newTemplate.selectedSkills.push(skill);
  }
}

async function saveTemplate() {
  const name = newTemplate.name.trim();
  const desc = newTemplate.desc.trim();
  if (!name || !desc || newTemplate.selectedSkills.length === 0) {
    return;
  }

  const payload = {
    name,
    type: newTemplate.type || '通用',
    description: desc,
    skills: [...newTemplate.selectedSkills]
  };

  try {
    if (editingTplId.value) {
      await updateActivityTemplate(editingTplId.value, payload);
    } else {
      await createActivityTemplate(payload);
    }
    activeModal.value = '';
    editingTplId.value = null;
    Object.assign(newTemplate, {
      name: '',
      type: '通用',
      desc: '',
      selectedSkills: []
    });
    await loadData();
  } catch (err) {
    error.value = err.message || '保存模板失败';
  }
}

function getSkillInfo(skillName) {
  return availableSkills.value.find(s => s.name === skillName) || { cat: '通用分析', desc: '' };
}

function openDeleteModal(tplId) {
  deletingTplId.value = tplId;
  activeModal.value = 'delete';
}

async function confirmDelete() {
  if (!deletingTplId.value) {
    activeModal.value = '';
    return;
  }
  try {
    await deleteActivityTemplate(deletingTplId.value);
    if (viewingTplId.value === deletingTplId.value) viewingTplId.value = null;
    activeModal.value = '';
    deletingTplId.value = null;
    await loadData();
  } catch (err) {
    error.value = err.message || '删除模板失败';
  }
}

onMounted(loadData);
</script>

<template>
  <div class="page">
    <div class="tpl-ph">
      <div>
        <div style="font-size: 15px; font-weight: 600; color: var(--t1)">活动分析模板</div>
        <div style="font-size: 12px; color: var(--t3); margin-top: 2px">预置分析框架，由多个 SKILL 组合而成，可快速应用至活动分析</div>
      </div>
      <button class="btn pri" @click="openNewTemplateModal">
        <i class="ti ti-plus"></i> 新增模板
      </button>
    </div>
    <div class="tpl-filter">
      <select v-model="filterType" style="width: 140px">
        <option>全部类型</option>
        <option>线上活动</option>
        <option>线下活动</option>
        <option>通用</option>
      </select>
      <input v-model="searchKeyword" style="width: 220px" placeholder="搜索模板名称...">
      <button class="btn"><i class="ti ti-search"></i></button>
      <span style="margin-left: auto; font-size: 12px; color: var(--t3)">共 {{ templateCount }} 个模板</span>
    </div>
    <div v-if="error" class="itip" style="margin: 10px 20px 0; border-color: var(--color-danger-border); background: var(--color-danger-weak); color: var(--danger)">
      <i class="ti ti-alert-circle"></i>{{ error }}
    </div>
    <div style="flex: 1; overflow-y: auto">
      <div class="tpl-grid">
        <div v-if="loading" style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--t3)">
          正在加载模板数据...
        </div>
        <div 
          v-for="tpl in filteredTemplates" 
          :key="tpl.id" 
          class="tpl-card"
          @click="viewTemplateDetail(tpl.id)"
        >
          <div class="tpl-card-header">
            <div style="display: flex; align-items: flex-start; gap: 10px; flex: 1">
              <div class="tpl-icon" :style="{ background: tpl.bg }">
                <i :class="'ti ' + tpl.icon" :style="{ color: tpl.color, fontSize: '18px' }"></i>
              </div>
              <div style="flex: 1; min-width: 0">
                <div class="tpl-name">{{ tpl.name }}</div>
                <div class="tpl-acts">
                  <span class="tag" :class="getTypeBadgeClass(tpl.type)" style="font-size: 11px">{{ tpl.type }}</span>
                </div>
              </div>
            </div>
            <div class="tpl-actions" @click.stop>
              <div class="aicon ed" title="编辑" @click="openEditTemplateModal(tpl.id)">
                <i class="ti ti-edit" style="font-size: 13px"></i>
              </div>
              <div class="aicon dl" title="删除" @click="openDeleteModal(tpl.id)">
                <i class="ti ti-trash" style="font-size: 13px"></i>
              </div>
            </div>
          </div>
          <div class="tpl-desc">{{ tpl.desc }}</div>
          <div class="tpl-skills">
            <div 
              v-for="(skill, index) in tpl.skills" 
              :key="skill" 
              class="tpl-skill-chip"
            >
              <div class="order-num">{{ index + 1 }}</div>
              {{ skill }}
            </div>
          </div>
          <div class="tpl-footer">
            <span class="tpl-meta">
              <i class="ti ti-apps" style="font-size: 12px; vertical-align: -1px"></i>
              {{ tpl.skills.length }} 个 SKILL · 已应用 {{ tpl.useCnt }} 次
            </span>
            <!-- <button class="btn sm pri" @click.stop="applyTemplate(tpl)">
              <i class="ti ti-player-play" style="font-size: 12px"></i> 应用
            </button> -->
          </div>
        </div>
        <div v-if="!loading && filteredTemplates.length === 0" style="grid-column: 1/-1; text-align: center; padding: 40px;">
          <i class="ti ti-inbox" style="font-size: 48px; color: var(--t3); margin-bottom: 12px;"></i>
          <div style="font-size: 13px; color: var(--t2);">暂无匹配的模板</div>
        </div>
      </div>
    </div>

    <!-- 新增/编辑模板弹窗 -->
    <ModalDialog
      :open="activeModal === 'new'"
      :title="editingTplId ? '编辑活动分析模板' : '新增活动分析模板'"
      :large="true"
      :close-on-backdrop="false"
      @close="activeModal = ''"
    >
      <div class="fg2" style="margin-bottom: 14px">
        <label class="fl">模板名称 <span class="req">*</span></label>
        <input v-model="newTemplate.name" class="fin" placeholder="如：外呼活动分析、多活动对比分析">
      </div>
      <div class="fg2" style="margin-bottom: 14px">
        <label class="fl">模板类型 <span class="req">*</span></label>
        <select v-model="newTemplate.type" class="fsel">
          <option>线上活动</option>
          <option>线下活动</option>
          <option>通用</option>
        </select>
      </div>
      <div class="fg2" style="margin-bottom: 14px">
        <label class="fl">模板描述 <span class="req">*</span></label>
        <input v-model="newTemplate.desc" class="fin" placeholder="描述该模板的分析场景与适用范围">
      </div>
      <div class="fg2">
        <label class="fl">选择并排序 SKILL 组件 <span class="req">*</span>
          <span style="color: var(--t3); font-weight: 400; margin-left: 6px">点击添加，拖拽调序，点击已选标签移除</span>
        </label>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px">
          <div>
            <div style="font-size: 11px; color: var(--t3); margin-bottom: 6px">全量 SKILL 库（点击添加）</div>
            <div class="skill-picker">
              <div 
                v-for="skill in availableSkills" 
                :key="skill.name"
                class="skill-pick-item"
                :class="{ chosen: newTemplate.selectedSkills.includes(skill.name) }"
                @click="toggleSkillSelection(skill.name)"
              >
                <div style="flex: 1">
                  <div class="spi-name">{{ skill.name }}</div>
                  <div style="display: flex; gap: 4px; margin-top: 2px">
                    <span class="tag tgr" style="font-size: 11px">{{ skill.cat }}</span>
                  </div>
                </div>
                <i v-if="newTemplate.selectedSkills.includes(skill.name)" class="ti ti-check" style="color: var(--primary); font-size: 14px"></i>
              </div>
            </div>
          </div>
          <div>
            <div style="font-size: 11px; color: var(--t3); margin-bottom: 6px">已选 SKILL 顺序（点击标签移除）</div>
            <div class="selected-skills-preview">
              <div v-if="newTemplate.selectedSkills.length === 0" class="ss-empty">尚未选择任何 SKILL</div>
              <div 
                v-for="(skill, index) in newTemplate.selectedSkills" 
                :key="skill" 
                class="ss-chip"
                @click="toggleSkillSelection(skill)"
              >
                <div class="order-num" style="width: 16px; height: 16px; font-size: 11px">{{ index + 1 }}</div>
                {{ skill }}
                <i class="ti ti-x" style="font-size: 10px"></i>
              </div>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <button class="btn pri" :disabled="!newTemplate.name.trim() || !newTemplate.desc.trim() || newTemplate.selectedSkills.length === 0" @click="saveTemplate">保存模板</button>
      </template>
    </ModalDialog>

    <!-- 模板详情弹窗 -->
    <ModalDialog :open="activeModal === 'detail'" :title="viewingTemplate?.name || '模板详情'" @close="activeModal = ''" :large="true">
      <div v-if="viewingTemplate" style="margin-bottom: 14px">
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px">
          <div class="tpl-icon" :style="{ background: viewingTemplate.bg, width: '44px', height: '44px', borderRadius: '10px' }">
            <i :class="'ti ' + viewingTemplate.icon" :style="{ color: viewingTemplate.color, fontSize: '22px' }"></i>
          </div>
          <div>
            <div style="font-size: 15px; font-weight: 600; color: var(--t1)">{{ viewingTemplate.name }}</div>
            <div style="margin-top: 4px; display: flex; gap: 6px; flex-wrap: wrap">
              <span class="tag" :class="getTypeBadgeClass(viewingTemplate.type)">{{ viewingTemplate.type }}</span>
              <span class="tag tgr">{{ viewingTemplate.skills.length }} 个 SKILL</span>
              <span class="tag tgr">已应用 {{ viewingTemplate.useCnt }} 次</span>
            </div>
          </div>
        </div>
        <div style="font-size: 12px; color: var(--t2); background: var(--bg-subtle); padding: 10px 12px; border-radius: var(--radius-xs); line-height: 1.6">{{ viewingTemplate.desc }}</div>
      </div>
      <div style="font-size: 12px; font-weight: 600; color: var(--t1); margin-bottom: 8px">SKILL 组件执行顺序</div>
      <div class="tpl-detail-skills">
        <div 
          v-for="(skill, index) in viewingTemplate?.skills" 
          :key="skill" 
          class="tpl-detail-skill"
        >
          <div class="tpl-ds-num">{{ index + 1 }}</div>
          <div class="tpl-ds-info">
            <div class="tpl-ds-name">{{ skill }}</div>
            <div class="tpl-ds-cat">
              <span class="tag tb2" style="font-size: 11px">{{ getSkillInfo(skill).cat }}</span>
              <span style="color: var(--t3); margin-left: 4px">{{ getSkillInfo(skill).desc }}</span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <button class="btn" @click="activeModal = ''">关闭</button>
        <button class="btn ghost" @click="editTemplateFromDetail">
          <i class="ti ti-edit"></i> 编辑模板
        </button>
        <!-- <button class="btn pri" @click="applyTemplateFromDetail">
          <i class="ti ti-player-play"></i> 应用此模板
        </button> -->
      </template>
    </ModalDialog>

    <!-- 删除确认弹窗 -->
    <ModalDialog :open="activeModal === 'delete'" title="确认删除" @close="activeModal = ''" :danger="true">
      <div style="padding: 8px 0;">
        <p style="font-size: 13px; color: var(--t1); line-height: 1.7">确定要删除该模板吗？</p>
        <p style="font-size: 12px; margin-top: 8px; background: var(--color-danger-weak); border-radius: var(--radius-xs); padding: 8px 10px; border-left: 3px solid var(--d); color: var(--t2)">删除后该模板无法恢复，请谨慎操作。</p>
      </div>
      <template #footer>
        <button class="btn" @click="activeModal = ''">取消</button>
        <button class="btn dbtn" @click="confirmDelete">确认删除</button>
      </template>
    </ModalDialog>
  </div>
</template>

<style scoped>
.tpl-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  padding: 16px 20px;
}
.tpl-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 16px;
  cursor: pointer;
  transition: .15s;
  position: relative;
}
.tpl-card:hover {
  border-color: var(--primary);
  box-shadow: var(--shadow-md);
}
.tpl-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
}
.tpl-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.tpl-acts {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.tpl-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--t1);
  margin-bottom: 4px;
}
.tpl-desc {
  font-size: 11px;
  color: var(--t3);
  line-height: 1.5;
  margin-bottom: 10px;
}
.tpl-skills {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-bottom: 10px;
}
.tpl-skill-chip {
  background: var(--bg-subtle);
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  padding: 2px 7px;
  font-size: 11px;
  color: var(--t2);
  display: flex;
  align-items: center;
  gap: 4px;
}
.tpl-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.tpl-meta {
  font-size: 11px;
  color: var(--t3);
}
.tpl-actions {
  display: flex;
  gap: 8px;
  opacity: 0;
  transition: .15s;
}
.tpl-card:hover .tpl-actions {
  opacity: 1;
}
.aicon {
  width: 26px;
  height: 26px;
  border-radius: var(--radius-xs);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--t2);
  transition: .15s;
}
.aicon.ed:hover {
  border-color: var(--primary);
  color: var(--primary);
  background: var(--pl);
}
.aicon.dl:hover {
  border-color: var(--danger);
  color: var(--danger);
  background: var(--color-danger-weak);
}
.skill-picker {
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  padding: 10px;
  background: var(--bg-subtle);
  max-height: 200px;
  overflow-y: auto;
}
.skill-pick-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-xs);
  cursor: pointer;
  transition: .15s;
}
.skill-pick-item:hover {
  background: #fff;
}
.skill-pick-item.chosen {
  background: var(--color-primary-weak);
}
.skill-pick-item.chosen .spi-name {
  color: var(--primary);
  font-weight: 500;
}
.spi-name {
  font-size: 12px;
  color: var(--t1);
}
.selected-skills-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 32px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xs);
  background: #fff;
}
.ss-chip {
  background: var(--pl);
  color: var(--primary);
  padding: 3px 8px;
  border-radius: var(--radius-xs);
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}
.ss-chip i {
  font-size: 11px;
}
.ss-empty {
  font-size: 11px;
  color: var(--t3);
  align-self: center;
}
.order-num {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.tpl-detail-skills {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.tpl-detail-skill {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: var(--bg-subtle);
  border-radius: var(--radius-xs);
  border: 1px solid var(--border);
}
.tpl-ds-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.tpl-ds-info {
  flex: 1;
}
.tpl-ds-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--t1);
}
.tpl-ds-cat {
  font-size: 11px;
  color: var(--t3);
  margin-top: 2px;
}

.tb2 { background: var(--color-primary-weak); color: var(--color-primary); }
.to { background: var(--color-warning-weak); color: var(--color-warning); }
.tpur { background: var(--color-violet-weak); color: var(--color-violet-text); }
.tgr { background: var(--bg-sunken); color: var(--t2); }

@media (max-width: 960px) {
  .tpl-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 640px) {
  .tpl-grid {
    grid-template-columns: 1fr;
  }
}
</style>

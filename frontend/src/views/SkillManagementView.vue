<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import ModalDialog from '../components/common/ModalDialog.vue';
import { createSkill, createSkillCategory, deleteSkillAPI, fetchSkillCategories, fetchSkills, deleteSkillCategory, updateSkill, updateSkillCategory } from '../api/skills';

const skills = ref([]);
const categoryOptions = ref([]);
const keyword = ref('');
const category = ref('全部分类');
const activeModal = ref('');
const editingSkill = ref(null);
const deletingSkill = ref(null);
const loading = ref(false);
const error = ref('');
const categoryForm = reactive({
  name: '',
  description: ''
});
const categoryManagementList = ref([]);
const DEFAULT_CATEGORY_NAME = '默认分类'; // 默认分类名称
const form = reactive({
  name: '',
  cat: '',
  desc: '',
  tpl: ''
});

const categories = computed(() => ['全部分类', ...categoryOptions.value.map((item) => item.name)]);
const filteredSkills = computed(() => skills.value.filter((skill) => {
  const matchCategory = category.value === '全部分类' || skill.cat === category.value;
  const matchKeyword = !keyword.value.trim() || skill.name.includes(keyword.value.trim());
  return matchCategory && matchKeyword;
}));

async function loadData() {
  loading.value = true;
  error.value = '';
  try {
    const [categoryList, skillList] = await Promise.all([
      fetchSkillCategories(),
      fetchSkills()
    ]);
    categoryOptions.value = categoryList;
    skills.value = skillList;
    if (category.value !== '全部分类' && !categories.value.includes(category.value)) {
      category.value = '全部分类';
    }
  } catch (err) {
    error.value = err.message || '数据加载失败';
  } finally {
    loading.value = false;
  }
}

function openCategoryModal() {
  categoryForm.name = '';
  categoryForm.description = '';
  activeModal.value = 'category';
}

function openCategoryManagementModal() {
  categoryManagementList.value = categoryOptions.value.map(item => ({
    ...item,
    skillCount: skills.value.filter(skill => skill.cat === item.name).length
  }));
  activeModal.value = 'categoryManagement';
}

function openSkillModal(skill = null) {
  editingSkill.value = skill;
  Object.assign(form, skill || { name: '', cat: categories.value[1] || '', desc: '', tpl: '' });
  activeModal.value = 'skill';
}

async function saveCategory() {
  if (!categoryForm.name.trim()) return;
  try {
    const created = await createSkillCategory({
      name: categoryForm.name.trim(),
      description: categoryForm.description.trim()
    });
    activeModal.value = '';
    await loadData();
    category.value = created.name;
  } catch (err) {
    error.value = err.message || '新增分类失败';
  }
}

async function addCategoryInManagement() {
  if (!categoryForm.name.trim()) return;
  try {
    await createSkillCategory({
      name: categoryForm.name.trim(),
      description: categoryForm.description.trim()
    });
    categoryForm.name = '';
    categoryForm.description = '';
    await loadData();
    // 刷新分类管理列表
    categoryManagementList.value = categoryOptions.value.map(item => ({
      ...item,
      skillCount: skills.value.filter(skill => skill.cat === item.name).length
    }));
  } catch (err) {
    error.value = err.message || '新增分类失败';
  }
}

async function deleteCategory(categoryName) {
  // 获取默认分类（第一个分类或名称为默认分类的）
  const defaultCategory = categoryOptions.value[0];
  if (!defaultCategory) {
    error.value = '系统错误：没有可用的分类';
    return;
  }
  
  // 默认分类不可删除
  if (categoryName === defaultCategory.name) {
    error.value = '默认分类不可删除';
    return;
  }
  
  try {
    // 找到要删除的分类 ID
    const categoryToDelete = categoryOptions.value.find(item => item.name === categoryName);
    if (!categoryToDelete) {
      error.value = '分类不存在';
      return;
    }
    
    // 将该分类下的所有技能迁移到默认分类
    const skillsToMigrate = skills.value.filter(skill => skill.cat === categoryName);
    
    if (skillsToMigrate.length > 0) {
      // 调用后端 API 批量更新技能分类
      for (const skill of skillsToMigrate) {
        await updateSkillCategory(skill.id, defaultCategory.id);
      }
    }
    
    // 调用后端 API 删除分类
    await deleteSkillCategory(categoryToDelete.id);
    
    // 重新加载数据以确保同步
    await loadData();
    
    // 刷新分类管理列表
    categoryManagementList.value = categoryOptions.value.map(item => ({
      ...item,
      skillCount: skills.value.filter(skill => skill.cat === item.name).length
    }));
    
    // 如果当前选中的是被删除的分类，切换回默认分类
    if (category.value === categoryName) {
      category.value = '全部分类';
    }
  } catch (err) {
    error.value = err.message || '删除分类失败';
  }
}

async function saveSkill() {
  if (!form.name.trim()) {
    activeModal.value = '';
    return;
  }
  if (editingSkill.value) {
    try {
      await updateSkill(editingSkill.value.id, {
        name: form.name.trim(),
        category_name: form.cat || categories.value.find((item) => item !== '全部分类') || '',
        description: form.desc || '自定义分析组件',
        template: form.tpl || '1. 数据处理\n2. 结果输出'
      });
      activeModal.value = '';
      await loadData();
    } catch (err) {
      error.value = err.message || '更新 SKILL 失败';
    }
    return;
  }

  try {
    const created = await createSkill({
      name: form.name.trim(),
      category_name: form.cat || categories.value.find((item) => item !== '全部分类') || '',
      description: form.desc || '自定义分析组件',
      template: form.tpl || '1. 数据处理\n2. 结果输出'
    });
    activeModal.value = '';
    await loadData();
    category.value = created.cat;
    keyword.value = '';
  } catch (err) {
    error.value = err.message || '新增 SKILL 失败';
  }
}

function openDeleteSkillModal(skill) {
  deletingSkill.value = skill;
  activeModal.value = 'skillDelete';
}

async function confirmDeleteSkill() {
  if (!deletingSkill.value) {
    activeModal.value = '';
    return;
  }
  try {
    await deleteSkillAPI(deletingSkill.value.id);
    activeModal.value = '';
    deletingSkill.value = null;
    await loadData();
  } catch (err) {
    error.value = err.message || '删除 SKILL 失败';
  }
}

onMounted(loadData);
</script>

<template>
  <div class="page">
    <div class="skph">
      <div>
        <div style="font-size: 15px; font-weight: 600">全量SKILL技能管理</div>
        <div class="subtitle">支持拖拽至编排区</div>
      </div>
      <div style="display: flex; gap: 8px">
        <button class="btn" type="button" @click="openCategoryManagementModal">分类管理</button>
        <button class="btn pri" type="button" @click="openSkillModal()">新增 SKILL</button>
      </div>
    </div>
    <div class="skfb">
      <select v-model="category" class="fsel" style="width: 140px">
        <option v-for="item in categories" :key="item">{{ item }}</option>
      </select>
      <input v-model="keyword" class="fi" placeholder="搜索技能名称" />
      <button class="btn" type="button"><i class="ti ti-search"></i></button>
    </div>
    <div v-if="error" class="itip" style="margin: 10px 20px 0; border-color: #ffd0d0; background: #fff5f5; color: var(--danger)">
      <i class="ti ti-alert-circle"></i>{{ error }}
    </div>
    <div class="sktw">
      <table class="skt">
        <thead>
          <tr>
            <th><input type="checkbox" class="ck" /></th>
            <th>SKILL名称</th>
            <th>分类</th>
            <th>简述</th>
            <th>模板预览</th>
            <th>已应用</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="7" style="text-align: center; color: var(--t3)">正在加载 SKILL 数据...</td>
          </tr>
          <tr v-for="skill in filteredSkills" :key="skill.name">
            <td><input type="checkbox" class="ck" /></td>
            <td>{{ skill.name }}</td>
            <td><span class="tag tb">{{ skill.cat }}</span></td>
            <td>{{ skill.desc }}</td>
            <td><span class="tprev">{{ skill.tpl }}</span></td>
            <td>{{ skill.useCnt || 0 }} 次</td>
            <td>
              <div class="aicons">
                <button class="aicon ed" type="button" aria-label="编辑" @click="openSkillModal(skill)">
                  <i class="ti ti-edit"></i>
                </button>
                <button class="aicon dl" type="button" aria-label="删除" @click="openDeleteSkillModal(skill)">
                  <i class="ti ti-trash"></i>
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="!loading && filteredSkills.length === 0">
            <td colspan="7" style="text-align: center; color: var(--t3)">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="pgn">
      <span>共 {{ filteredSkills.length }} 条</span>
      <div class="pgb active">1</div>
    </div>

    <ModalDialog :open="activeModal === 'category'" title="新增分类" @close="activeModal = ''">
      <div class="fg2">
        <label class="fl">分类名称</label>
        <input v-model="categoryForm.name" class="fin" placeholder="例如：渠道分析" @keydown.enter="saveCategory" />
      </div>
      <div class="fg2">
        <label class="fl">分类说明</label>
        <input v-model="categoryForm.description" class="fin" placeholder="可选" @keydown.enter="saveCategory" />
      </div>
      <template #footer>
        <button class="btn" type="button" @click="activeModal = ''">取消</button>
        <button class="btn pri" type="button" :disabled="!categoryForm.name.trim()" @click="saveCategory">保存</button>
      </template>
    </ModalDialog>

    <ModalDialog :open="activeModal === 'categoryManagement'" title="分类管理" @close="activeModal = ''" width="600">
      <div style="margin-bottom: 16px; display: flex; gap: 8px; align-items: center;">
        <input v-model="categoryForm.name" class="fin" placeholder="分类名称" style="flex: 1;" />
        <input v-model="categoryForm.description" class="fin" placeholder="分类说明" style="flex: 1;" />
        <button class="btn pri" type="button" :disabled="!categoryForm.name.trim()" @click="addCategoryInManagement">添加</button>
      </div>
      <div class="sktw" style="max-height: 400px; overflow-y: auto;">
        <table class="skt">
          <thead>
            <tr>
              <th>分类名称</th>
              <th>分类说明</th>
              <th>技能数量</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in categoryManagementList" :key="item.name">
              <td>
                <span class="tag tb">{{ item.name }}</span>
                <span v-if="index === 0" style="margin-left: 6px; font-size: 12px; color: var(--t3)">(默认)</span>
              </td>
              <td>{{ item.description || '-' }}</td>
              <td>{{ item.skillCount }}</td>
              <td>
                <div class="aicons">
                  <button 
                    v-if="index !== 0"
                    class="aicon dl" 
                    type="button" 
                    aria-label="删除"
                    @click="deleteCategory(item.name)"
                  >
                    <i class="ti ti-trash"></i>
                  </button>
                  <span v-else style="color: var(--t3); font-size: 12px;">不可删除</span>
                </div>
              </td>
            </tr>
            <tr v-if="categoryManagementList.length === 0">
              <td colspan="4" style="text-align: center; color: var(--t3)">暂无分类</td>
            </tr>
          </tbody>
        </table>
      </div>
      <template #footer>
        <button class="btn" type="button" @click="activeModal = ''">关闭</button>
      </template>
    </ModalDialog>

    <ModalDialog
      :open="activeModal === 'skill'"
      :title="editingSkill ? '编辑SKILL' : '新增SKILL'"
      :close-on-backdrop="false"
      @close="activeModal = ''"
    >
      <div class="fg2">
        <label class="fl">技能名称</label>
        <input v-model="form.name" class="fin" />
      </div>
      <div class="fg2">
        <label class="fl">分类</label>
        <select v-model="form.cat" class="fsel">
          <option v-for="item in categories.filter((item) => item !== '全部分类')" :key="item">{{ item }}</option>
        </select>
      </div>
      <div class="fg2">
        <label class="fl">简述</label>
        <input v-model="form.desc" class="fin" placeholder="可选，简述该技能的作用" />
      </div>
      <div class="fg2">
        <label class="fl">执行模板</label>
        <textarea v-model="form.tpl" class="fta"></textarea>
      </div>
      <template #footer>
        <button class="btn pri" type="button" @click="saveSkill">保存</button>
      </template>
    </ModalDialog>

    <ModalDialog :open="activeModal === 'skillDelete'" title="确认删除" @close="activeModal = ''" :danger="true">
      <div style="padding: 8px 0;">
        <p style="font-size: 13px; color: var(--t1); line-height: 1.7">确定要删除该 SKILL 吗？</p>
        <p v-if="deletingSkill" style="font-size: 12px; color: var(--t2); margin-top: 6px">
          SKILL名称：<strong>{{ deletingSkill.name }}</strong>
        </p>
        <p style="font-size: 12px; margin-top: 8px; background: #FFF3F3; border-radius: 4px; padding: 8px 10px; border-left: 3px solid var(--d); color: var(--t2)">删除后该 SKILL 将不再出现在技能列表和模板组件选择中，请谨慎操作。</p>
      </div>
      <template #footer>
        <button class="btn" type="button" @click="activeModal = ''">取消</button>
        <button class="btn dbtn" type="button" @click="confirmDeleteSkill">确认删除</button>
      </template>
    </ModalDialog>
  </div>
</template>
